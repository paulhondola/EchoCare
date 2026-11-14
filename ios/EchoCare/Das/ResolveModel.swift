import Foundation
import Observation

/// „Rezolvare caz”: POST /incidents/{id}/resolve with an outcome and a note (UC-11 step 4), ported
/// from android/app's das/ResolveViewModel.kt. It reads nothing, so no background read can wipe
/// what is being typed.
@Observable @MainActor
final class ResolveModel {
    var outcome: String?
    var note = ""

    private(set) var sending = false

    /// Why the last Trimite was refused; what was typed stays.
    private(set) var notice: DasNotice?

    /// Resolved: the screen leaves.
    private(set) var done = false

    private let id: String
    private let api: ApiClient

    init(id: String, api: ApiClient = ApiClient(tokens: FirebaseTokenSource())) {
        self.id = id
        self.api = api
    }

    func submit() async {
        guard let picked = outcome, canSend(picked, note), !sending else { return }
        sending = true
        let id = id
        let api = api
        let body = Resolution(outcome: picked, note: note.trimmingCharacters(in: .whitespacesAndNewlines))
        switch await send({ try await api.resolve(id: id, body: body) }) {
        case .ok: done = true
        case .no(let refusal): notice = noticeAfter(refusal, act: .resolve)
        }
        sending = false
    }
}
