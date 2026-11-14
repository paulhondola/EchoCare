import Foundation

// What a read answered and what a page shows, ported from android/app/.../home/Load.kt (seniors
// §8.2). LoadTests.swift ports LoadTest.kt.

/// What a refused or failed read means for the person (auth-layer §3.2, seniors §8.2).
enum Failure: CaseIterable, Sendable {
    case noConnection, notFound, notAllowed, signedOut, notRegistered

    /// The app returns to sign-in: a grant revoked mid-session ends the session this way.
    var endsSession: Bool { self == .signedOut || self == .notRegistered }
}

/// `status` is the HTTP status, or nil when no answer came at all.
func failureOf(status: Int?, reason: String?) -> Failure {
    switch status {
    // A 401 arrives only after ApiClient's retry with a fresh token.
    case 401: .signedOut
    case 403 where reason == "not_registered": .notRegistered
    case 403: .notAllowed
    case 404: .notFound
    // No answer, a 5xx, or a status this build does not know: the last data stays up.
    default: .noConnection
    }
}

/// The reason in a refusal body, `{"detail": {"reason": …}}` (04 §0); nil for any other body.
func reasonOf(_ body: String?) -> String? {
    // FastAPI's own 422 has a list under "detail"; a proxy's error page is not JSON at all.
    guard let body,
        let root = try? JSONSerialization.jsonObject(with: Data(body.utf8)) as? [String: Any],
        let detail = root["detail"] as? [String: Any]
    else { return nil }
    return detail["reason"] as? String
}

/// What a read answered.
enum Answer<T: Sendable>: Sendable {
    case ok(T)
    case no(Failure)
}

extension Answer: Equatable where T: Equatable {}

/// The HTTP status of a failed call; nil when no answer came (a lost connection, a cancel).
func statusOf(_ error: Error) -> Int? {
    if case ApiError.http(let status, _) = error { return status }
    return nil
}

/// Runs `call`. A refusal, a lost connection or an unreadable body becomes what it means.
func answer<T: Sendable>(_ call: @Sendable () async throws -> T) async -> Answer<T> {
    do {
        return .ok(try await call())
    } catch ApiError.http(let status, let body) {
        return .no(failureOf(status: status, reason: reasonOf(body)))
    } catch TokenError.signedOut {
        // Android sends no header then, and the API answers 401
        return .no(.signedOut)
    } catch {
        // No connection, a timeout, a cancel, or an answer that is not the expected type
        return .no(.noConnection)
    }
}

/// What a list or a page shows (seniors §8.2).
enum Load<T: Sendable>: Sendable {
    case loading
    /// `offline`: the last read failed, so `value` is the last data, under the banner (06 §1).
    case ready(T, offline: Bool = false)
    case failed(Failure)

    /// The state after `answer`. With data on screen, losing the connection keeps the data.
    func after(_ answer: Answer<T>) -> Load<T> {
        switch answer {
        case .ok(let value):
            return .ready(value)
        case .no(let failure):
            if failure == .noConnection, case .ready(let value, _) = self {
                return .ready(value, offline: true)
            }
            return .failed(failure)
        }
    }
}

extension Load: Equatable where T: Equatable {}
