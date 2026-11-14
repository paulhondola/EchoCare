import FirebaseAuth
import SwiftUI

/// What the app shows for `AuthModel.screen` (android/app's MainActivity.kt `setContent`).
struct RootView: View {
    let auth: AuthModel

    var body: some View {
        Group {
            switch auth.screen {
            // Signed in: the role's home and what opens from it (seniors §8.2).
            case .home(let role, let displayName, let roles):
                HomeNav(role: role, displayName: displayName, roles: roles, auth: auth).id(role)
            case .landing:
                LandingView(onSignIn: auth.openSignIn)
            default:
                SignInView(auth: auth)
            }
        }
        // One dark theme (spec 07 §2.1): light status bar whatever the system uses
        .preferredColorScheme(.dark)
        .task { await auth.start() }
        // Firebase's reCAPTCHA page returns through the Encoded App ID URL scheme
        // (Config/EchoCare-Info.plist). A SwiftUI app is scene-based, so the URL reaches the scene,
        // not the app delegate; Firebase's scene-delegate swizzling may catch it first, in which
        // case canHandle answers false here and nothing happens twice.
        .onOpenURL { url in _ = Auth.auth().canHandle(url) }
    }
}

/// The sign-in steps on the dashboard's panel, centred, scrolling over the keyboard.
private struct SignInView: View {
    let auth: AuthModel

    // Kept across the loading spinner, so a refused number or a wrong code can be corrected
    @State private var phone = ""
    @State private var code = ""

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                Group {
                    if auth.screen == .loading {
                        VStack(spacing: 24) {
                            ProgressView().tint(Theme.fgMuted).controlSize(.large)
                            // Only while a code is sent or checked, not during GET /me
                            if auth.signingIn {
                                SnButton("back", kind: .outline, action: auth.abandonSignIn)
                            }
                        }
                    } else {
                        SignInPanel { step }
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, minHeight: geometry.size.height)
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .background(Theme.canvas.ignoresSafeArea())
    }

    @ViewBuilder private var step: some View {
        switch auth.screen {
        case .phone(let error):
            PhoneView(phone: $phone, error: error, onSendCode: send)
        // Signed out already: the phone form, under the not-registered text (auth-layer §3.2).
        case .notRegistered:
            PhoneView(phone: $phone, error: "not_registered", onSendCode: send)
        case .code(let error):
            CodeView(
                code: $code,
                error: error,
                canResend: auth.canResend,
                onConfirm: { entered in Task { await auth.verify(code: entered) } },
                onResend: { Task { await auth.resend() } })
        case .unavailable:
            ErrorText(key: "unavailable")
            SnButton("retry", kind: .link, fullWidth: true) { Task { await auth.loadMe() } }
            SnButton("sign_out", kind: .outline, fullWidth: true, action: auth.signOut)
        case .pickRole(let roles):
            PickRoleView(roles: roles, onPick: auth.pick(role:))
        default:
            EmptyView()
        }
        // Before anyone is signed in, Înapoi returns to the landing page
        switch auth.screen {
        case .phone, .code, .notRegistered:
            SnButton("back", kind: .outline, fullWidth: true, action: auth.backToLanding)
        default:
            EmptyView()
        }
    }

    private func send(_ number: String) {
        code = ""
        Task { await auth.sendCode(phone: number) }
    }
}
