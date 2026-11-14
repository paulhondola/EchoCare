import SwiftUI

/// What a `Load` shows (seniors §8.2), ported from android's `LoadBody` (home/Frame.kt). A failure
/// that ends the session is handed to `onSessionEnd`.
struct LoadBody<T: Sendable, Content: View>: View {
    let load: Load<T>
    let onRetry: () -> Void
    let onSessionEnd: (Failure) -> Void
    @ViewBuilder let content: (T) -> Content

    private var ended: Failure? {
        if case .failed(let failure) = load, failure.endsSession { failure } else { nil }
    }

    var body: some View {
        Group {
            switch load {
            case .loading:
                ProgressView().tint(Theme.fgMuted).controlSize(.large)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .ready(let value, let offline):
                VStack(spacing: 0) {
                    // The last data stays under the banner (06 §1)
                    if offline { Banner("offline_banner", tone: .galben) }
                    content(value)
                }
            case .failed(let failure):
                switch failure {
                case .noConnection:
                    Message("no_connection") { SnButton("retry", kind: .link, action: onRetry) }
                case .notFound: Message("not_found")
                case .notAllowed: Message("not_allowed")
                // The session is ending: sign-in replaces this screen.
                case .signedOut, .notRegistered: EmptyView()
                }
            }
        }
        .onChange(of: ended, initial: true) { _, failure in
            if let failure { onSessionEnd(failure) }
        }
    }
}

/// One sentence, flush left as everything on the dashboard, with an optional action under it.
struct Message<Action: View>: View {
    let key: String
    @ViewBuilder let action: Action

    init(_ key: String, @ViewBuilder action: () -> Action = { EmptyView() }) {
        self.key = key
        self.action = action()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(LocalizedStringKey(key)).textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgMuted)
            action
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear { AccessibilityNotification.Announcement(String(localized: .init(key))).post() }
    }
}
