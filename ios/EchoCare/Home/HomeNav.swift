import SwiftUI

/// Where the signed-in app can go from a role's home (android/app's home/Routes.kt).
enum HomeRoute: Hashable {
    case profile
    /// Monitorizare: the medic's patients by group (UC-12, 03 §7).
    case monitor
    /// One senior's page.
    case senior(id: String)
    /// „Pacient nou”: the medic's form, empty, or filled from the senior `id` (seniors §9.1).
    case enroll(id: String?)
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
    /// „Trimis la DAS.” on the medic home after the form submits (Task 10 sets it).
    @State private var sent = false

    var body: some View {
        // Only the medic registers seniors (04 §2): the form's entry points are hers (seniors §9.1)
        let medic = role == "medic"
        NavigationStack(path: $path) {
            RoleHome(role: role, onSessionEnd: sessionEnded, open: { path.append($0) }, sent: $sent)
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
                    case .monitor:
                        MonitorView(
                            onBack: { pop(.monitor) },
                            onOpen: { path.append(.senior(id: $0)) },
                            onNew: { path.append(.enroll(id: nil)) },
                            onEdit: { path.append(.enroll(id: $0)) },
                            onSessionEnd: sessionEnded
                        )
                    case .senior(let id):
                        SeniorPageView(
                            id: id,
                            onBack: { pop(route) },
                            onSessionEnd: sessionEnded,
                            onEdit: medic ? { path.append(.enroll(id: $0)) } : nil
                        )
                    case .enroll(let id):
                        EnrollView(seniorId: id, onLeave: { pop(route) })
                    }
                }
        }
        .environment(\.signedIn, displayName)
        // Not twice on top of itself, as Android's launchSingleTop
        .environment(\.openProfile, OpenProfileAction { if path.last != .profile { path.append(.profile) } })
    }

    private func sessionEnded(_ failure: Failure) {
        auth.sessionEnded(notRegistered: failure == .notRegistered)
    }

    /// Back by route, as Android pops by route: a second tap never pops the home.
    private func pop(_ route: HomeRoute) {
        if let at = path.lastIndex(of: route) { path.removeSubrange(at...) }
    }
}
