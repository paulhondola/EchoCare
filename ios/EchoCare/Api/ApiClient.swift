import FirebaseAuth
import Foundation

// The FastAPI client (04-interfaces.md), ported from Android's EchoCareApi and its OkHttp
// interceptor (Modules.kt): one method per endpoint, the Firebase token on every request, one retry
// on 401 with a fresh token. savePushToken and dropPushToken are not ported: iOS has no push.

/// What a failed call says. Anything else thrown (a `URLError`, `TokenError`) is passed through.
enum ApiError: Error {
    /// A non-2xx answer (a 401 only after the retry); [body] is the raw response text.
    case http(status: Int, body: String)
    /// A 2xx answer that is not the expected type.
    case decoding(Error)
}

/// Where the bearer token comes from. `forceRefresh` is set on the retry after a 401.
protocol TokenSource: Sendable {
    func token(forceRefresh: Bool) async throws -> String
}

enum TokenError: Error {
    case signedOut
}

/// The signed-in Firebase user's ID token; the SDK caches it and refreshes when it nears expiry.
struct FirebaseTokenSource: TokenSource {
    func token(forceRefresh: Bool) async throws -> String {
        guard let user = Auth.auth().currentUser else { throw TokenError.signedOut }
        return try await user.getIDToken(forcingRefresh: forceRefresh)
    }
}

actor ApiClient {
    private let baseURL: URL
    private let tokens: TokenSource
    private let session: URLSession

    init(baseURL: URL = AppConfig.apiURL, tokens: TokenSource, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.tokens = tokens
        self.session = session
    }

    /// Lenient like Android's `Json { ignoreUnknownKeys = true }`: unknown keys are ignored, and the
    /// types keep enum-like values as strings. Dates stay strings.
    static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }

    // MARK: Profile

    func me() async throws -> Me { try await get("profile") }

    // MARK: Seniors

    /// The seniors the caller reaches as [role]; the server narrows the list (seniors SE6).
    func seniors(role: String) async throws -> [SeniorRow] {
        try await get("seniors", query: [URLQueryItem(name: "role", value: role)])
    }

    func senior(id: String) async throws -> SeniorPage { try await get("seniors/\(seg(id))") }

    /// The senior's calls, newest first, queued ones included (04 §1).
    func calls(id: String) async throws -> [CallRow] { try await get("seniors/\(seg(id))/calls") }

    /// A new senior in `draft`, registered by the calling medic (04 §2). Not repeat-safe (SE14).
    func createSenior(_ body: SeniorForm) async throws -> SeniorPage {
        try await post("seniors", body: body)
    }

    /// The whole registration again, in any state (04 §2, SE9).
    func updateSenior(id: String, body: SeniorForm) async throws -> SeniorPage {
        try await decoded(send("PUT", "seniors/\(seg(id))", json: body))
    }

    func addCaregiver(id: String, body: CaregiverForm) async throws -> Caregiver {
        try await post("seniors/\(seg(id))/caregivers", body: body)
    }

    /// 204, also on a repeat (04 §2).
    func removeCaregiver(id: String, userId: String) async throws {
        _ = try await send("DELETE", "seniors/\(seg(id))/caregivers/\(seg(userId))")
    }

    /// `draft` → `submitted`: DAS sees the senior from now on (04 §2). Answers one row.
    func submit(id: String) async throws -> SeniorRow { try await post("seniors/\(seg(id))/submit") }

    /// Queues the welcome call again; answers the senior's row (04 §2, UC-04).
    func callAgain(id: String) async throws -> SeniorRow {
        try await post("seniors/\(seg(id))/welcome-call")
    }

    /// Records that the senior withdrew her consent by phone; answers her row (04 §2).
    func withdraw(id: String) async throws -> SeniorRow {
        try await post("seniors/\(seg(id))/consent-withdrawn")
    }

    /// Stores the signed consent, 204 (04 §2).
    func sign(id: String, body: SignatureForm) async throws {
        _ = try await send("POST", "seniors/\(seg(id))/signature", json: body)
    }

    // MARK: Medical record

    /// 200 with the record; nil for 204, none attached (design §5.7). Only a 204 is "none": a 404
    /// throws like any other non-2xx, so a caller keeps its previous record, as Android's
    /// SeniorViewModel.kt does (it clears `medical` on 204 alone).
    func medicalRecord(id: String) async throws -> MedicalRecord? {
        try await optional("GET", "seniors/\(seg(id))/medical-record", nilOn: [204])
    }

    /// The raw PDF, `application/pdf`, at most 10 MB (design §5.7).
    func uploadMedicalRecord(id: String, pdf: Data) async throws -> MedicalRecord {
        try await decoded(
            send("PUT", "seniors/\(seg(id))/medical-record", body: pdf, contentType: "application/pdf"))
    }

    func confirmMedicalRecord(id: String, body: MedicalConfirmForm) async throws -> MedicalRecord {
        try await post("seniors/\(seg(id))/medical-record/confirm", body: body)
    }

    func reanalyzeMedicalRecord(id: String) async throws -> MedicalRecord {
        try await post("seniors/\(seg(id))/medical-record/reanalyze")
    }

    // MARK: Mock call (demo)

    /// The due call; nil for 204, none due, or 404, production (design §4.2).
    func mockCall() async throws -> MockCall? {
        try await optional("GET", "profile/mock-call", nilOn: [204, 404])
    }

    /// 204; a 409 means the call is no longer due (design §4.2), thrown as `ApiError.http`.
    func mockAnswer(id: String, body: MockAnswer) async throws {
        _ = try await send("POST", "calls/\(seg(id))/mock-answer", json: body)
    }

    // MARK: Senior's device

    /// Senior only. 204, also on a repeat (04 §3).
    func checkIn(_ body: CheckInForm) async throws {
        _ = try await send("POST", "me/check-ins", json: body)
    }

    /// Senior only. 200 also for a duplicate; `callId` is nil when no call was queued (04 §3).
    func sendEvent(_ body: EventForm) async throws -> EventResult {
        try await post("me/events", body: body)
    }

    // MARK: Incidents (DAS)

    /// DAS only. [status] is comma-separated; the DAS app asks for `open,in_progress` (04 §1).
    func incidents(status: String) async throws -> [IncidentRow] {
        try await get("incidents", query: [URLQueryItem(name: "status", value: status)])
    }

    func incident(id: String) async throws -> IncidentPage { try await get("incidents/\(seg(id))") }

    /// One call's turns (04 §1): the incident page's call; its `answers` are ignored.
    func transcript(id: String) async throws -> IncidentCall { try await get("calls/\(seg(id))/transcript") }

    /// `open` → `in_progress` (UC-11). 409 `already_done` names who has it in `taken_by_name`.
    func take(id: String) async throws -> IncidentRow { try await post("incidents/\(seg(id))/take") }

    /// `in_progress` → `resolved`, by any DAS employee (UC-11). 409 `wrong_state` while open.
    func resolve(id: String, body: Resolution) async throws -> IncidentRow {
        try await post("incidents/\(seg(id))/resolve", body: body)
    }

    // MARK: Transport

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try await decoded(send("GET", path, query: query))
    }

    private func post<T: Decodable>(_ path: String) async throws -> T {
        try await decoded(send("POST", path))
    }

    private func post<T: Decodable>(_ path: String, body: some Encodable) async throws -> T {
        try await decoded(send("POST", path, json: body))
    }

    /// The decoded body of a 2xx; nil for a status in [nilOn].
    private func optional<T: Decodable>(
        _ method: String, _ path: String, nilOn: Set<Int>
    ) async throws -> T? {
        let (data, status) = try await raw(method, path)
        if nilOn.contains(status) { return nil }
        return try decoded(check(data, status))
    }

    private func decoded<T: Decodable>(_ data: Data) throws -> T {
        do {
            return try Self.makeDecoder().decode(T.self, from: data)
        } catch {
            throw ApiError.decoding(error)
        }
    }

    private func send(
        _ method: String, _ path: String, query: [URLQueryItem] = [], json: some Encodable
    ) async throws -> Data {
        let body = try Self.makeEncoder().encode(json)
        return try await send(method, path, query: query, body: body, contentType: "application/json")
    }

    /// The body of a 2xx answer; anything else throws `ApiError.http`.
    private func send(
        _ method: String, _ path: String, query: [URLQueryItem] = [], body: Data? = nil,
        contentType: String? = nil
    ) async throws -> Data {
        let (data, status) = try await raw(
            method, path, query: query, body: body, contentType: contentType)
        return try check(data, status)
    }

    private func check(_ data: Data, _ status: Int) throws -> Data {
        guard (200..<300).contains(status) else {
            throw ApiError.http(status: status, body: String(decoding: data, as: UTF8.self))
        }
        return data
    }

    /// One request with the bearer, sent again once with a fresh token on 401 (as Modules.kt's
    /// interceptor does). Answers whatever status the server ends on.
    private func raw(
        _ method: String, _ path: String, query: [URLQueryItem] = [], body: Data? = nil,
        contentType: String? = nil
    ) async throws -> (Data, Int) {
        let (data, status) = try await attempt(
            method, path, query, body, contentType, forceRefresh: false)
        guard status == 401 else { return (data, status) }
        return try await attempt(method, path, query, body, contentType, forceRefresh: true)
    }

    private func attempt(
        _ method: String, _ path: String, _ query: [URLQueryItem], _ body: Data?,
        _ contentType: String?, forceRefresh: Bool
    ) async throws -> (Data, Int) {
        var request = URLRequest(url: try url(path, query))
        request.httpMethod = method
        request.setValue("Bearer \(try await tokens.token(forceRefresh: forceRefresh))", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        return (data, http.statusCode)
    }

    /// Every route is under `<apiURL>/api/`.
    private func url(_ path: String, _ query: [URLQueryItem]) throws -> URL {
        var root = baseURL.absoluteString
        while root.hasSuffix("/") { root.removeLast() }
        guard var components = URLComponents(string: "\(root)/api/\(path)") else {
            throw URLError(.badURL)
        }
        if !query.isEmpty { components.queryItems = query }
        guard let url = components.url else { throw URLError(.badURL) }
        return url
    }

    /// One path segment, an id: nothing in it can add a slash or a query.
    private func seg(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlPathSegment) ?? value
    }
}

private extension CharacterSet {
    static let urlPathSegment = CharacterSet(
        charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
}
