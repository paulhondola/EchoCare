import SwiftUI

// The sign-in steps of android/app's MainActivity.kt (`SignIn`, `Panel`, `PhoneForm`).

/// The dashboard's sign-in panel: the brand, a 2pt rule, then the step.
struct SignInPanel<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                BrandMark(size: 32)
                Text("app_name").textCase(.uppercase).textStyle(Theme.titleLarge).foregroundStyle(
                    Theme.fg)
            }
            Rule()
            content
        }
        .padding(24)
        .frame(maxWidth: 420, alignment: .leading)
        .background(Theme.subtle)
        .overlay(Rectangle().strokeBorder(Theme.line, lineWidth: 2))
    }
}

struct SignInTitle: View {
    let key: LocalizedStringKey

    init(_ key: LocalizedStringKey) { self.key = key }

    var body: some View {
        Text(key).textStyle(Theme.headlineSmall).foregroundStyle(Theme.fg)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The phone step. `error` is a `Localizable.xcstrings` key; signed out already, `not_registered`
/// shows here, over the form (auth-layer §3.2).
struct PhoneView: View {
    @Binding var phone: String
    let error: String?
    let onSendCode: (String) -> Void

    var body: some View {
        SignInTitle("sign_in_title")
        SnTextField(
            text: $phone, label: "phone_label", keyboard: .phonePad, content: .telephoneNumber)
        if let error { ErrorText(key: error) }
        SnButton("send_code", kind: .link, fullWidth: true) { onSendCode(toE164(phone)) }
            .disabled(phone.trimmingCharacters(in: .whitespaces).isEmpty)
    }
}
