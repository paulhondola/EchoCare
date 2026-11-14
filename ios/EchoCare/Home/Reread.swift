import SwiftUI

/// Android's `RereadWhileShown` (home/Frame.kt): reads when the screen appears and every
/// `AppConfig.rereadSeconds` while it is shown (06 §3). iOS has no push (design, Out of scope), so
/// the timer is the only refresh. `.task` cancels on disappear; the scene phase stops it in the
/// background and reads again on return, as `repeatOnLifecycle(STARTED)` does.
struct Reread: ViewModifier {
    let load: @MainActor () async -> Void

    @Environment(\.scenePhase) private var phase

    func body(content: Content) -> some View {
        let shown = phase != .background
        content.task(id: shown) {
            guard shown else { return }
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(AppConfig.rereadSeconds))
            }
        }
    }
}

extension View {
    /// `.reread { await model.load() }`: see `Reread`.
    func reread(_ load: @escaping @MainActor () async -> Void) -> some View {
        modifier(Reread(load: load))
    }
}
