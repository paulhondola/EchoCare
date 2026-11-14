import SwiftUI

/// Several roles and none picked yet (auth-layer §8.2, MainActivity.kt `Screen.PickRole`).
struct PickRoleView: View {
    let roles: [String]
    let onPick: (String) -> Void

    var body: some View {
        SignInTitle("pick_role_title")
        ForEach(roles, id: \.self) { role in
            SnButton(LocalizedStringKey(roleLabels[role] ?? role), fullWidth: true) { onPick(role) }
        }
    }
}
