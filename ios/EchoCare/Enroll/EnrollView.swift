import SwiftUI

// Placeholders for Task 10, which replaces this file: the medic's form („Pacient nou”, „Editează
// datele”, seniors §9.1) and the consent text with its signature pad (G7). Until then each says it
// is coming, so the medic home's entry points already lead somewhere.

/// „Pacient nou”: empty, or filled from the senior `seniorId`.
struct EnrollView: View {
    let seniorId: String?
    let onLeave: () -> Void

    var body: some View {
        Frame(String(localized: "new_patient"), onBack: onLeave) {
            Message("coming_on_ios")
        }
        // No profile from a form: switching role there would drop what was typed
        .environment(\.openProfile, nil)
    }
}

/// The consent text and a pad to sign it on (G7, UC-01 step 5); `onSave` gets what to post.
struct ConsentSection: View {
    let signedAt: String?
    let busy: Bool
    let onSave: (SignatureForm) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionLabel("consent_label")
            if let signedAt {
                Text(verbatim: localized("signed_on", shortDate(signedAt, year: true)))
                    .textStyle(Theme.titleMedium).foregroundStyle(Theme.verdeFg)
            } else {
                Text("coming_on_ios").textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgMuted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
