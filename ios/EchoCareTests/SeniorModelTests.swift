import Foundation
import Testing

@testable import EchoCare

// „Pornește monitorizarea” says what happened, not what was hoped (design, Monitoring).
@MainActor
struct SeniorModelTests {
    private struct NoToken: TokenSource {
        func token(forceRefresh: Bool) async throws -> String { "t" }
    }

    private func model(start: @escaping @MainActor () async throws -> Void) -> SeniorModel {
        SeniorModel(api: ApiClient(tokens: NoToken()), startWatch: start)
    }

    @Test func aStartThatThrowsIsFailedNotStarted() async {
        let model = model { throw WatchLinkError.notAvailable }
        await model.startMonitoring()
        #expect(model.monitoring == .failed)
    }

    @Test func aStartThatWorksIsStarted() async {
        let model = model {}
        await model.startMonitoring()
        #expect(model.monitoring == .started)
    }

    @Test func theStubDoesNotPretend() async {
        await #expect(throws: WatchLinkError.self) { try await WatchLink.shared.startMonitoring() }
    }
}
