import SwiftUI

/// Where the signed-in app can go from a role's home. Later tasks add their pages here.
enum HomeRoute: Hashable {
    case profile
}

/// The signed-in app: the role's home and what opens from it (seniors §8.2), ported from
/// android/app/.../home/HomeNav.kt. Permissions are FastAPI's; this only picks screens (G3).
/// RootView gives it `.id(role)`: a new stack for a new role, so that role's home is the root.
struct HomeNav: View {
    let role: String
    let displayName: String
    let roles: [String]
    let auth: AuthModel

    @State private var path: [HomeRoute] = []

    var body: some View {
        NavigationStack(path: $path) {
            RoleHome(role: role) { failure in auth.sessionEnded(notRegistered: failure == .notRegistered) }
                .navigationDestination(for: HomeRoute.self) { route in
                    switch route {
                    case .profile:
                        ProfileView(
                            role: role,
                            displayName: displayName,
                            roles: roles,
                            phone: auth.signedInPhone,
                            onBack: { pop(.profile) },
                            onPickRole: auth.switchRole(to:),
                            onSignOut: auth.signOut
                        )
                    }
                }
        }
        .environment(\.signedIn, displayName)
        // Not twice on top of itself, as Android's launchSingleTop
        .environment(\.openProfile, OpenProfileAction { if path.last != .profile { path.append(.profile) } })
    }

    /// Back by route, as Android pops ProfileRoute: a second tap never pops the home.
    private func pop(_ route: HomeRoute) {
        if let at = path.lastIndex(of: route) { path.removeSubrange(at...) }
    }
}
