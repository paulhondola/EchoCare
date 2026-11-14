import SwiftUI

// What every signed-in screen is built from (seniors §8.2), ported from android/app/.../home/Frame.kt.
// The ⋮ menu went in 3d3e80b: the top bar holds nothing of the app's own; the profile opens from
// the person's square, which carries role switching and Ieșire (design 2026-11-13 medic home).

extension EnvironmentValues {
    /// The signed-in person's name, for the top bar on every screen (UC-12, 04 §1 `/profile`).
    @Entry var signedIn: String?

    /// Opens the profile page from the person's square in the top bar (design 2026-11-13 medic
    /// home); nil on the profile page itself and outside the signed-in app.
    @Entry var openProfile: OpenProfileAction?
}

/// What `openProfile` holds: a struct rather than a bare closure, as SwiftUI's own `OpenURLAction`.
struct OpenProfileAction {
    let run: @MainActor () -> Void

    @MainActor func callAsFunction() { run() }
}

/// The frame every signed-in screen shares: a title, a back arrow or none, the screen's own button
/// (the medic home's „Pacient nou”, Android's menu slot) and the person's square. It hides the
/// navigation bar: this top bar is the dashboard's, as on Android.
struct Frame<Content: View>: View {
    let title: String
    let onBack: (() -> Void)?
    let trailing: AnyView?
    @ViewBuilder let content: Content

    init(_ title: String, onBack: (() -> Void)? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.onBack = onBack
        self.trailing = nil
        self.content = content()
    }

    init(
        _ title: String, onBack: (() -> Void)? = nil, @ViewBuilder trailing: () -> some View,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.onBack = onBack
        self.trailing = AnyView(trailing())
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 0) {
            TopBar(title: title, onBack: onBack, trailing: trailing)
            content.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        // Pinned to the top also when the content takes no room
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Theme.canvas)
        .toolbar(.hidden, for: .navigationBar)
    }
}

/// The dashboard's header on a phone: brand over the title, square buttons, a 2pt rule.
private struct TopBar: View {
    let title: String
    let onBack: (() -> Void)?
    let trailing: AnyView?

    @Environment(\.signedIn) private var signedIn
    @Environment(\.openProfile) private var openProfile
    @State private var wide = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                if let onBack {
                    SquareIconButton(systemImage: "arrow.left", description: "back", action: onBack)
                }
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 6) {
                        BrandMark(size: 16)
                        SectionLabel("app_name")
                    }
                    Text(title)
                        .textStyle(Theme.titleLarge)
                        .foregroundStyle(Theme.fg)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .accessibilityAddTraits(.isHeader)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let trailing { trailing }
                let name = signedIn ?? ""
                if openProfile != nil || !name.trimmingCharacters(in: .whitespaces).isEmpty {
                    SignedIn(name: name, wide: wide, onOpen: openProfile)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            Rule()
        }
        .background(Theme.subtle.ignoresSafeArea(edges: .top))
        .onGeometryChange(for: Bool.self) {
            $0.size.width >= 600
        } action: {
            wide = $0
        }
    }
}

/// The person's square, and their name on a wide screen. With `onOpen` it is the button to the
/// profile page; a name with no letters, such as "Dr.", gets an icon there so the page stays reachable.
private struct SignedIn: View {
    let name: String
    let wide: Bool
    let onOpen: OpenProfileAction?

    var body: some View {
        let letters = initials(name)
        if letters.isEmpty, let onOpen {
            SquareIconButton(systemImage: "ellipsis", description: "profile") { onOpen() }
        } else if let onOpen {
            // The only way to Ieșire and role switching: a full 48pt target, as ⋮ was
            Button {
                onOpen()
            } label: {
                square(letters, border: Theme.link)
                    .frame(minWidth: 48, minHeight: 48)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(Text("profile"))
            .accessibilityAddTraits(.isButton)
        } else {
            square(letters, border: Theme.lineStrong)
        }
    }

    private func square(_ letters: String, border: Color) -> some View {
        HStack(spacing: 8) {
            // A name of titles only, such as "Dr.", has no letters: no empty square
            if !letters.isEmpty {
                Text(verbatim: letters)
                    .textStyle(Theme.labelMedium)
                    .foregroundStyle(Theme.fg)
                    .frame(width: 28, height: 28)
                    .background(Theme.card)
                    .overlay(Rectangle().strokeBorder(border, lineWidth: 1))
            }
            if wide {
                Text(verbatim: name)
                    .textStyle(Theme.bodyMedium)
                    .foregroundStyle(Theme.fg)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
        }
    }
}
