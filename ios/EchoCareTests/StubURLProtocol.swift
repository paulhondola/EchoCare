import Foundation
import os

/// Answers every request of a session built with `StubURLProtocol.session(...)` from a closure, and
/// records what was sent. State is per stub, keyed by a header, so suites can run in parallel.
final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    struct Sent: Sendable {
        let method: String
        let url: URL
        let headers: [String: String]
        let body: Data
    }

    struct Reply: Sendable {
        var status: Int
        var body: Data
        init(_ status: Int, _ body: String = "") {
            self.status = status
            self.body = Data(body.utf8)
        }
    }

    final class Stub: Sendable {
        fileprivate let id = UUID().uuidString
        private let state = OSAllocatedUnfairLock(initialState: [Sent]())
        fileprivate let handler: @Sendable (Sent) -> Reply

        init(_ handler: @escaping @Sendable (Sent) -> Reply) {
            self.handler = handler
            registry.withLock { $0[id] = self }
        }

        var requests: [Sent] { state.withLock { $0 } }
        fileprivate func record(_ sent: Sent) { state.withLock { $0.append(sent) } }

        func session() -> URLSession {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.protocolClasses = [StubURLProtocol.self]
            configuration.httpAdditionalHeaders = [StubURLProtocol.header: id]
            return URLSession(configuration: configuration)
        }
    }

    private static let header = "X-Stub-Id"
    private static let registry = OSAllocatedUnfairLock(initialState: [String: Stub]())

    /// A stub that answers [replies] in order, then repeats the last.
    static func replying(_ replies: Reply...) -> Stub {
        let next = OSAllocatedUnfairLock(initialState: 0)
        return Stub { _ in
            let index = next.withLock { n -> Int in
                defer { n += 1 }
                return min(n, replies.count - 1)
            }
            return replies[index]
        }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let id = request.value(forHTTPHeaderField: Self.header),
            let stub = Self.registry.withLock({ $0[id] }), let url = request.url
        else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        var headers = request.allHTTPHeaderFields ?? [:]
        headers[Self.header] = nil
        let sent = Sent(
            method: request.httpMethod ?? "GET", url: url, headers: headers, body: bodyData())
        stub.record(sent)
        let reply = stub.handler(sent)
        let response = HTTPURLResponse(
            url: url, statusCode: reply.status, httpVersion: "HTTP/1.1", headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: reply.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    /// URLSession turns `httpBody` into a stream before it reaches a protocol.
    private func bodyData() -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }
}
