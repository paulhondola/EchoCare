import FirebaseAuth
import Foundation
import Observation
import os

// Ported from android/app/.../auth/AuthViewModel.kt and the sign-in half of MainActivity.kt.
// No push on iOS (design, Out of scope), so nothing here saves or drops a push token.

private let savedRole = "role"
private let log = Logger(subsystem: "ro.echocare.ios", category: "EchoCareAuth")

/// Phone sign-in, then GET /me (auth-layer §8.2, UC-02). Nothing here touches Firebase before
/// `start()`: the app creates this model before the app delegate runs `FirebaseApp.configure()`.
@Observable @MainActor
final class AuthModel {
    private(set) var screen: Screen = .landing

    /// *Retrimite codul* opens 30 seconds after a code is sent (auth-layer §8.2).
    private(set) var canResend = false

    /// The E.164 number the code went to. iOS has no resend token: a resend verifies it again.
    private(set) var phone = ""

    /// The spinner is a sign-in step (sending the code, or checking it) rather than GET /me, so
    /// *Înapoi* under it can abandon the attempt.
    private(set) var signingIn = false

    /// The number Firebase signed in, for the profile page; nil hides it.
    var signedInPhone: String? { Auth.auth().currentUser?.phoneNumber }

    private let api: ApiClient
    // The picked role survives a restart (auth-layer §8.2).
    private let defaults: UserDefaults
    private var verificationID = ""
    private var me: Me?
    private var started = false
    private var resendTimer: Task<Void, Never>?

    /// Firebase can't cancel a verification, so each code sent, and each step back to the landing,
    /// starts a new attempt: an answer from an older one changes nothing.
    private var attempt = 0

    init(
        api: ApiClient = ApiClient(tokens: FirebaseTokenSource()),
        defaults: UserDefaults = .standard
    ) {
        self.api = api
        self.defaults = defaults
    }

    /// Once, when the app's first view appears: signed in from an earlier run, straight to /me.
    func start() async {
        guard !started else { return }
        started = true
        if Auth.auth().currentUser != nil { await loadMe() }
    }

    /// *Intrați* on the landing page.
    func openSignIn() {
        screen = .phone()
    }

    /// Back from the phone or code step, before anyone is signed in.
    func backToLanding() {
        attempt += 1
        signingIn = false
        screen = .landing
    }

    /// *Înapoi* under the spinner while a code is sent or checked: Firebase may never answer (a
    /// reCAPTCHA page left open, no network). Starts a new attempt, so the late answer is dropped,
    /// and opens the phone form again. Android has no such way back; iOS's reCAPTCHA flow needs it.
    func abandonSignIn() {
        guard signingIn else { return }
        attempt += 1
        signingIn = false
        screen = .phone()
    }

    /// *Trimite codul*. With app verification on (REAL_SMS = YES) Firebase opens its reCAPTCHA page
    /// by itself, as there is no APNs; the page returns through the Encoded App ID URL scheme,
    /// which RootView hands to `Auth.auth().canHandle(_:)`.
    func sendCode(phone: String) async {
        self.phone = phone
        screen = .loading
        signingIn = true
        attempt += 1
        let current = attempt
        do {
            let id = try await PhoneAuthProvider.provider().verifyPhoneNumber(
                phone, uiDelegate: nil)
            guard current == attempt else { return }
            signingIn = false
            verificationID = id
            codeSent()
        } catch {
            guard current == attempt else { return }
            signingIn = false
            logFailure("Sending the code", error)
            screen = .phone(error: sendError(error))
        }
    }

    /// *Retrimite codul*: a new verification of the same number.
    func resend() async {
        await sendCode(phone: phone)
    }

    /// *Confirmă* with the code from the SMS.
    func verify(code: String) async {
        screen = .loading
        signingIn = true
        let current = attempt
        let credential = PhoneAuthProvider.provider().credential(
            withVerificationID: verificationID, verificationCode: code)
        do {
            _ = try await Auth.auth().signIn(with: credential)
        } catch {
            guard current == attempt else { return }
            signingIn = false
            logFailure("Signing in with the code", error)
            let wrong = [.invalidVerificationCode, .sessionExpired].contains(authCode(of: error))
            screen = .code(error: wrong ? "wrong_code" : "unavailable")
            return
        }
        guard current == attempt else {
            // Abandoned, then signed in after all: don't stay signed in behind the phone form
            if screen != .loading { signOutOfFirebase() }
            return
        }
        signingIn = false
        // GET /me has no way back, as on Android
        await loadMe()
    }

    /// GET /me after sign-in, at start and on *Reîncercați*.
    func loadMe() async {
        screen = .loading
        let next: Screen
        do {
            let me = try await api.me()
            self.me = me
            next = screenFor(me, saved: defaults.string(forKey: savedRole))
        } catch ApiError.http(let status, _) {
            next = screenFor(status: status)
        } catch TokenError.signedOut {
            // Android sends no header then, and the API answers 401
            next = screenFor(status: 401)
        } catch {
            // No connection, a timeout, or an answer that isn't a profile
            next = .unavailable
        }
        show(next)
    }

    /// A role from the picker, saved for the next start.
    func pick(role: String) {
        guard let me else { return }
        defaults.set(role, forKey: savedRole)
        show(.home(role: role, displayName: me.displayName, roles: rolesOf(me)))
    }

    /// One tap on another role on the profile page (design 2026-11-13 medic home): the same as
    /// picking it, as Android's `pickRole` serves both.
    func switchRole(to role: String) {
        pick(role: role)
    }

    /// *Ieșire*.
    func signOut() {
        show(.landing)
    }

    /// A read after sign-in was refused as signed out or not registered (seniors §8.2): a grant
    /// revoked mid-session ends the session, with the not-registered text. Signed out, it opens the
    /// phone form rather than the landing, as a 401 from /me does: this person was just signed in.
    func sessionEnded(notRegistered: Bool) {
        show(notRegistered ? .notRegistered : .phone())
    }

    private func codeSent() {
        screen = .code()
        canResend = false
        resendTimer?.cancel()
        resendTimer = Task {
            try? await Task.sleep(for: .seconds(30))
            if !Task.isCancelled { canResend = true }
        }
    }

    private func show(_ next: Screen) {
        switch next {
        // auth-layer §3.2: not_registered and a second 401 sign out of Firebase.
        case .phone, .notRegistered, .landing:
            signOutOfFirebase()
            defaults.removeObject(forKey: savedRole)
        // A saved role that is no longer among the grants is dropped (auth-layer §8.2).
        case .pickRole:
            defaults.removeObject(forKey: savedRole)
        default:
            break
        }
        screen = next
    }

    private func signOutOfFirebase() {
        // Every path that ends the session: no more Health readings under the next sign-in
        HealthSync.shared.stop()
        do {
            try Auth.auth().signOut()
        } catch {
            log.warning("Signing out failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    private func sendError(_ error: Error) -> String {
        switch authCode(of: error) {
        case .invalidPhoneNumber, .missingPhoneNumber: "invalid_phone"
        case .tooManyRequests, .quotaExceeded: "too_many_attempts"
        default: "unavailable"
        }
    }

    private func authCode(of error: Error) -> AuthErrorCode? {
        let ns = error as NSError
        return ns.domain == AuthErrors.domain ? AuthErrorCode(rawValue: ns.code) : nil
    }

    /// Firebase's own reason for a failed sign-in step, for Console.app (category EchoCareAuth). The
    /// screen shows only a short Romanian text (auth-layer §3.2), which hides codes such as 17028.
    private func logFailure(_ step: String, _ error: Error) {
        let ns = error as NSError
        log.warning(
            "\(step, privacy: .public) failed: \(ns.domain, privacy: .public) \(ns.code) \(ns.localizedDescription, privacy: .public)"
        )
    }
}
