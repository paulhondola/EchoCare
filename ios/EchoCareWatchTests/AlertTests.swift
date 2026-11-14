import Shared
import Testing

@testable import EchoCareWatch

// The confirmation's phases and the prompt's draining ring (design 2026-11-14, watch senior UI).
struct AlertTests {
    @Test func phaseIsSendingBeforeTheRetryLimit() {
        #expect(Alert(id: "e", sentAtMs: 0).phase(nowMs: 19_999) == .sending)
    }

    @Test func phaseIsRetryingFromTheRetryLimit() {
        #expect(Alert(id: "e", sentAtMs: 0).phase(nowMs: 20_000) == .retrying)
    }

    @Test func phaseIsReceivedOnceAcked() {
        #expect(Alert(id: "e", sentAtMs: 0, receivedAtMs: 25_000).phase(nowMs: 25_000) == .received)
    }

    // A second, panicked tap on the help button lands on this screen: it must not close it while
    // the alert is still being sent
    @Test func aSendingAlertCannotBeDismissed() {
        #expect(!Alert(id: "e", sentAtMs: 0).canDismiss(nowMs: 200))
    }

    @Test func aRetryingOrReceivedAlertCanBeDismissed() {
        #expect(Alert(id: "e", sentAtMs: 0).canDismiss(nowMs: 20_000))
        #expect(Alert(id: "e", sentAtMs: 0, receivedAtMs: 1_000).canDismiss(nowMs: 1_000))
    }

    @Test func remainingFractionRunsFromOneToZero() {
        let p = Prompt(
            id: "p", type: "fall", measuredAt: "", snapshot: .empty,
            deadlineMs: 1_000 + Timings.promptTimeoutMs)
        #expect(p.remainingFraction(nowMs: 1_000) == 1)
        #expect(p.remainingFraction(nowMs: 1_000 + Timings.promptTimeoutMs / 2) == 0.5)
        #expect(p.remainingFraction(nowMs: p.deadlineMs + 5_000) == 0)
        // A clock before the prompt opened
        #expect(p.remainingFraction(nowMs: 0) == 1)
    }
}
