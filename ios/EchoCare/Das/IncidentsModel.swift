import Foundation
import Observation

/// The DAS home: GET /incidents?status=open,in_progress (04 §1, UC-12), ported from
/// android/app's das/IncidentsViewModel.kt.
@Observable @MainActor
final class IncidentsModel {
    private(set) var incidents: Load<[IncidentRow]> = .loading

    /// The time "acum …" is counted to. Unchanged data is an equal state that redraws nothing, so
    /// the time is its own state, set on every re-read.
    private(set) var now = Date()

    private let api: ApiClient

    init(api: ApiClient = ApiClient(tokens: FirebaseTokenSource())) {
        self.api = api
    }

    /// Called when the screen appears and on every timed re-read (06 §3).
    func load() async {
        let api = api
        let read = await answer { try await api.incidents(status: ACTIVE) }
        // A cancelled read says nothing about the connection
        guard !Task.isCancelled else { return }
        now = Date()
        incidents = incidents.after(read)
    }
}
