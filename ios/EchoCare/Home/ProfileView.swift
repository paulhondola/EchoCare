import SwiftUI

// Ported from android/app/.../home/Profile.kt. Its *Notificări* section ("Alerte pe acest telefon")
// is left out: iOS has no push (design, Out of scope), so the row could only ever say "Oprite".

/// What each role's home shows, one line under its name on the profile page.
private let roleLines = [
    "das": "role_line_das",
    "medic": "role_line_medic",
    "caregiver": "role_line_caregiver",
    "senior": "role_line_senior",
]

/// The profile page (design 2026-11-13 medic home): who is signed in, the roles they may switch
/// between in one tap, and *Ieșire*. `phone` comes from the Firebase sign-in; nil hides it.
struct ProfileView: View {
    let role: String
    let displayName: String
    let roles: [String]
    let phone: String?
    let onBack: () -> Void
    let onPickRole: (String) -> Void
    let onSignOut: () -> Void

    var body: some View {
        Frame(String(localized: "profile"), onBack: onBack) {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Who(name: displayName, phone: phone)
                    SectionLabel("profile_role").padding(.top, 16)
                    ForEach(roles, id: \.self) { each in
                        RoleRow(role: each, current: each == role) { onPickRole(each) }
                    }
                    SnButton("sign_out", kind: .danger, fullWidth: true, action: onSignOut)
                        .padding(.top, 24)
                }
                .padding(16)
                .frame(maxWidth: 600)
                .frame(maxWidth: .infinity)
            }
        }
        // Its own square would open this page again
        .environment(\.openProfile, nil)
    }
}

private struct Who: View {
    let name: String
    let phone: String?

    var body: some View {
        HStack(spacing: 12) {
            let letters = initials(name)
            if !letters.isEmpty {
                Text(verbatim: letters)
                    .textStyle(Theme.titleLarge)
                    .foregroundStyle(Theme.fg)
                    .frame(width: 56, height: 56)
                    .background(Theme.card)
                    .overlay(Rectangle().strokeBorder(Theme.lineStrong, lineWidth: 1))
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: name).textStyle(Theme.titleLarge).foregroundStyle(Theme.fg)
                if let phone {
                    Text(verbatim: formatPhone(phone)).textStyle(Theme.mono).foregroundStyle(Theme.fgMuted)
                }
            }
        }
    }
}

/// One role: the current one marked and still; another switches to it on a tap.
private struct RoleRow: View {
    let role: String
    let current: Bool
    let onPick: () -> Void

    var body: some View {
        if current {
            row.accessibilityElement(children: .combine).accessibilityAddTraits(.isSelected)
        } else {
            Button(action: onPick) { row.contentShape(Rectangle()) }.buttonStyle(.plain)
        }
    }

    private var row: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(LocalizedStringKey(roleLabels[role] ?? role))
                    .textStyle(Theme.titleMedium)
                    .foregroundStyle(Theme.fg)
                Text(LocalizedStringKey(roleLines[role] ?? ""))
                    .textStyle(Theme.bodyMedium)
                    .foregroundStyle(Theme.fgMuted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if current {
                Chip("role_active", tone: .link)
            } else {
                Text(verbatim: "→").textStyle(Theme.titleMedium).foregroundStyle(Theme.link)
                    .accessibilityHidden(true)
            }
        }
        .padding(12)
        .background(Theme.card)
        .overlay(Rectangle().strokeBorder(current ? Theme.link : Theme.card, lineWidth: 2))
    }
}
