import Foundation
import Observation

/// One incident: GET /incidents/{id} (04 §1, UC-11), ported from android/app's
/// das/IncidentViewModel.kt.
@Observable @MainActor
final class IncidentModel {
    let id: String

    private(set) var page: Load<IncidentPage> = .loading

    /// Why the last Preiau was refused; nil after a success.
    private(set) var notice: DasNotice?

    /// The time "acum …" is counted to; its own state, as `IncidentsModel.now`.
    private(set) var now = Date()

    /// While Preiau is being sent: the button is off and timed reads wait.
    private(set) var taking = false

    private let api: ApiClient
    private var reading: Task<Void, Never>?

    init(id: String, api: ApiClient = ApiClient(tokens: FirebaseTokenSource())) {
        self.id = id
        self.api = api
    }

    /// Called when the screen appears and on every timed re-read (06 §3).
    func load() async {
        now = Date()
        if taking { return }
        let id = id
        let api = api
        let read = Task {
            let read = await answer { try await api.incident(id: id) }
            // A read cancelled by Preiau says nothing, and must not land after it
            guard !Task.isCancelled else { return }
            // The page has moved on from what the notice was about
            if case .ok = read { notice = nil }
            page = page.after(read)
        }
        reading = read
        await withTaskCancellationHandler {
            await read.value
        } onCancel: {
            read.cancel()
        }
    }

    /// *Preiau* (UC-11 step 2). A refusal means the page is stale, so it is read again.
    func take() async {
        if taking { return }
        taking = true
        // A read sent before the take could land after it and bring Preiau back
        reading?.cancel()
        let id = id
        let api = api
        switch await send({ try await api.take(id: id) }) {
        case .ok: notice = nil
        case .no(let refusal): notice = noticeAfter(refusal, act: .take)
        }
        if case .ends? = notice {
        } else {
            page = page.after(await answer { try await api.incident(id: id) })
        }
        taking = false
    }
}
