import Foundation

// The medic's commands on her patient, „Sună din nou” and the withdrawal (UC-04, UC-12, 04 §2), and
// what each answer means for the page. Ported from android/app/.../home/Commands.kt. Android's
// `command(call)` runs a call through the enrollment form's `send`; here `command(_:)` turns what
// the API client threw into the status and body `commandOutcome` reads.

/// What a command answered. The page rereads after `done` and `refused`; `offline` keeps the page
/// as it is.
enum CommandOutcome: Equatable {
    case done
    /// The server said no; `reason` is a 409's reason, "not_found" for a 404, "invalid" for a 422,
    /// nil for a 403 or anything else.
    case refused(String?)
    /// No answer, or a 5xx: nothing is known to have changed (seniors §8.2).
    case offline
}

/// The outcome of HTTP `status` with `body`; a nil status is no answer at all.
func commandOutcome(status: Int?, body: String?) -> CommandOutcome {
    if let status, (200...299).contains(status) { return .done }
    let reason = reasonOf(body)
    switch status {
    case 422:
        // The body is FastAPI's list of fields, or `incomplete` with what is missing
        return .refused("invalid")
    case 409:
        // wrong_state, or a reason a later server adds: the senior is read again
        return .refused(["already_done", "phone_taken"].contains(reason) ? reason : "wrong_state")
    default:
        switch failureOf(status: status, reason: reason) {
        case .noConnection: return .offline
        case .notFound: return .refused("not_found")
        default: return .refused(nil)
        }
    }
}

/// Runs `call`: a refusal is read from its status and body, an unreadable body or no answer at all
/// is no connection, and the timed reread shows where the senior stands.
func command(
    isolation: isolated (any Actor)? = #isolation, _ call: () async throws -> Void
) async -> CommandOutcome {
    do {
        try await call()
        return .done
    } catch ApiError.http(let status, let body) {
        return commandOutcome(status: status, body: body)
    } catch TokenError.signedOut {
        // Android sends no header then, and the API answers 401
        return commandOutcome(status: 401, body: nil)
    } catch {
        // A URLError, a cancel, or a 2xx that is not the expected type
        return commandOutcome(status: nil, body: nil)
    }
}

/// The notice once a reread went through: the connection is back, so „Fără conexiune” goes. A
/// refusal stays until the next command.
func noticeAfterRead(_ notice: CommandOutcome?) -> CommandOutcome? {
    notice == .offline ? nil : notice
}

/// A number saved in the form for a senior the calls could not reach: no call is queued for it
/// (04 §2), so the page says to press „Sună din nou”. `before` is the number the page showed when
/// „Editează datele” was pressed.
func isNewNumberToCall(before: String, now: SeniorPage) -> Bool {
    now.phone != before && ["wrong_number", "unreachable"].contains(now.state)
}
