import Foundation

// What a refused command means for the form (seniors §9.3). Pure, ported from
// android/app/.../enroll/Refusal.kt; RefusalTests.swift ports RefusalTest.kt.

/// A refused command, read from either body: FastAPI's own 422 or ours (04 §0).
enum Refusal: Equatable, Sendable {
    /// FastAPI's 422, `{"detail": [{"loc": ["body", …]}]}`: the body fields it names.
    case invalid([String])
    /// 422 `incomplete`: what DAS still needs, named in `missing` (04 §2).
    case incomplete([String])
    /// 409 `already_done`; an incident taken by someone else names them (04 §2).
    case alreadyDone(takenByName: String? = nil)
    /// 409 `phone_taken`: the mobile already belongs to another senior (SE10).
    case phoneTaken
    /// The senior moved on meanwhile.
    case wrongState
    /// Anything else means what it means for a read (seniors §8.2).
    case failed(Failure)
}

/// The refusal in HTTP `status` and its `body`. A nil status is no answer at all.
func refusalOf(status: Int?, body: String?) -> Refusal {
    let detail = detailOf(body)
    let ours = detail as? [String: Any]
    let reason = ours?["reason"] as? String
    switch status {
    case 422:
        if let list = detail as? [Any] {
            var fields: [String] = []
            for name in list.compactMap(fieldOf) where !fields.contains(name) { fields.append(name) }
            return .invalid(fields)
        }
        if reason == "incomplete" {
            return .incomplete((ours?["missing"] as? [Any])?.compactMap { $0 as? String } ?? [])
        }
        return .invalid([])
    case 409:
        if reason == "already_done" { return .alreadyDone(takenByName: ours?["taken_by_name"] as? String) }
        if reason == "phone_taken" { return .phoneTaken }
        // wrong_state, or a reason a later server adds: the senior is read again
        return .wrongState
    default:
        return .failed(failureOf(status: status, reason: reason))
    }
}

/// `detail` of a JSON object body: a list for FastAPI's 422, an object for ours. A proxy's error
/// page is not JSON at all.
private func detailOf(_ body: String?) -> Any? {
    guard let body,
        let root = try? JSONSerialization.jsonObject(with: Data(body.utf8)) as? [String: Any]
    else { return nil }
    return root["detail"]
}

/// `loc` is ["body", "phone"] for a field of the body; a path or the whole body names none.
private func fieldOf(_ error: Any) -> String? {
    guard let loc = (error as? [String: Any])?["loc"] as? [Any], loc.count >= 2,
        loc[0] as? String == "body"
    else { return nil }
    return loc[1] as? String
}

/// What a command answered.
enum Sent<T: Sendable>: Sendable {
    case ok(T)
    case no(Refusal)
}

extension Sent: Equatable where T: Equatable {}

/// Runs `call`. A refusal, a lost connection or an unreadable body becomes what it means: Android's
/// `send`, as `command(_:)` (Home/Commands.swift) is its `Sent`-less sibling for the medic's page.
func send<T: Sendable>(
    isolation: isolated (any Actor)? = #isolation, _ call: () async throws -> T
) async -> Sent<T> {
    do {
        return .ok(try await call())
    } catch ApiError.http(let status, let body) {
        return .no(refusalOf(status: status, body: body))
    } catch TokenError.signedOut {
        // Android sends no header then, and the API answers 401
        return .no(refusalOf(status: 401, body: nil))
    } catch {
        // A URLError, a cancel, or a 2xx that is not the expected type
        return .no(.failed(.noConnection))
    }
}

/// The form's commands.
enum Action: CaseIterable, Sendable { case save, add, remove, submit, sign }

/// One line over the form's buttons.
enum Notice: Equatable, Sendable {
    /// `text` is a `Localizable.xcstrings` key.
    case says(String)
    /// „Lipsesc: …”, by the labels in `MISSING_LABELS`.
    case missing([String])
}

/// What the form does after a refused command (seniors §9.3).
enum Then: Equatable, Sendable {
    /// A text (a `Localizable.xcstrings` key) under each field the server named.
    case mark([Field: String])
    case show(Notice)
    /// Read the senior again; step 4 shows the state they are in.
    case reread
    /// The form cannot go on, as in slice 3's table (seniors §8.2).
    case stop(Failure)
}

func thenAfter(_ action: Action, _ refusal: Refusal) -> Then {
    switch refusal {
    case .invalid(let fields):
        return marks(action, fields)
    case .incomplete(let missing):
        // Past draft the last caregiver stays (04 §2)
        return action == .remove ? .show(.says("last_caregiver")) : .show(.missing(missing))
    case .alreadyDone:
        // A repeated submit: already submitted, so step 4 shows that
        return action == .add ? .show(.says("already_caregiver")) : .reread
    case .phoneTaken:
        return .mark([.phone: "phone_taken"])
    case .wrongState:
        return .reread
    case .failed(let failure):
        // The form keeps what was typed
        return failure == .noConnection ? .show(.says("no_connection")) : .stop(failure)
    }
}

/// The fields of the body `action` sent that FastAPI named by `keys`.
private func marks(_ action: Action, _ keys: [String]) -> Then {
    let sent: [Field] =
        switch action {
        case .save: REGISTRATION
        case .add: Step.caregivers.fields
        case .remove, .submit, .sign: []
        }
    var errors: [Field: String] = [:]
    for key in keys {
        guard let field = sent.first(where: { $0.key == key }) else { continue }
        errors[field] =
            switch field {
            case .phone: "invalid_phone"
            case .caregiverPhone: "caregiver_phone_invalid"
            default: "field_invalid"
            }
    }
    return errors.isEmpty ? .show(.says("field_invalid")) : .mark(errors)
}
