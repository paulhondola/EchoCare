import SwiftUI

/// The code step (MainActivity.kt `CodeForm`). iOS offers the SMS code above the keyboard
/// (`.oneTimeCode`), as Android reads it automatically.
struct CodeView: View {
    @Binding var code: String
    let error: String?
    let canResend: Bool
    let onConfirm: (String) -> Void
    let onResend: () -> Void

    var body: some View {
        SignInTitle("sign_in_title")
        SnTextField(text: $code, label: "code_label", keyboard: .numberPad, content: .oneTimeCode)
        if let error { ErrorText(key: error) }
        SnButton("confirm", kind: .success, fullWidth: true) { onConfirm(code) }
            .disabled(code.trimmingCharacters(in: .whitespaces).isEmpty)
        SnButton("resend_code", kind: .outline, fullWidth: true, action: onResend)
            .disabled(!canResend)
    }
}
