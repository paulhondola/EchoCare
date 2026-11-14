import Foundation
import Observation

/// The seniors the caller reaches in `role`: GET /seniors?role= (seniors SE6), ported from
/// android/app's home/SeniorsViewModel.kt and, for the medic's home and Monitorizare, the
/// MedicViewModel of home/MedicHome.kt (UC-12). Each screen holds its own. `selected` is
/// Monitorizare's chosen patient on a tablet.
@Observable @MainActor
final class SeniorsModel {
    let role: String

    private(set) var seniors: Load<[SeniorRow]> = .loading

    var selected: String?

    private let api: ApiClient

    init(role: String, api: ApiClient = ApiClient(tokens: FirebaseTokenSource())) {
        self.role = role
        self.api = api
    }

    /// Called when the screen appears, on every timed re-read (06 §3) and after a command on the
    /// patient beside the list.
    func load() async {
        let api = api
        let role = role
        let read = await answer { try await api.seniors(role: role) }
        // A cancelled read says nothing about the connection
        guard !Task.isCancelled else { return }
        seniors = seniors.after(read)
    }
}
