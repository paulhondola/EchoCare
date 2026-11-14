import Foundation

// The medic's commands on her patient, „Sună din nou” and the withdrawal (UC-04, UC-12, 04 §2), and
// what each answer means for the page. Ported from android/app/.../home/Commands.kt: `command(_:)`
// runs a call through the enrollment form's `send` (Enroll/Refusal.swift), the one place an error
// becomes an answer, and `outcomeOf` says what that answer means for the page.

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
    return outcomeOf(refusalOf(status: status, body: body))
}

/// What `refusal` means for the page, as `send` reads it for the form (seniors §9.3).
func outcomeOf(_ refusal: Refusal) -> CommandOutcome {
    switch refusal {
    // refusalOf reads wrong_state and a 409 reason this build does not know alike
    case .wrongState: .refused("wrong_state")
    case .alreadyDone: .refused("already_done")
    case .phoneTaken: .refused("phone_taken")
    case .failed(let failure):
        switch failure {
        case .noConnection: .offline
        case .notFound: .refused("not_found")
        default: .refused(nil)
        }
    // The body is FastAPI's list of fields, or `incomplete` with what is missing
    case .invalid, .incomplete: .refused("invalid")
    }
}

/// Runs `call` through the form's `send`, so both read an answer alike: an unreadable body is no
/// connection, and the timed reread shows where the senior stands.
func command(
    isolation: isolated (any Actor)? = #isolation, _ call: () async throws -> Void
) async -> CommandOutcome {
    switch await send(call) {
    case .ok: .done
    case .no(let refusal): outcomeOf(refusal)
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
