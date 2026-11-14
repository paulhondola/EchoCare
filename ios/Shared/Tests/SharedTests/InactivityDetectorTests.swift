import Testing
@testable import Shared

struct InactivityDetectorTests {
    @Test("fires once when the gap first crosses the limit")
    func firesOnceAtLimit() {
        let d = InactivityDetector(limitMs: 60_000)
        d.onStep(atMs: 0)
        #expect(!d.isInactive(nowMs: 59_000))
        #expect(d.isInactive(nowMs: 60_000))
    }

    @Test("does not fire twice without a reset")
    func doesNotFireTwice() {
        let d = InactivityDetector(limitMs: 60_000)
        d.onStep(atMs: 0)
        #expect(d.isInactive(nowMs: 60_000))
        #expect(!d.isInactive(nowMs: 120_000))
    }

    @Test("a step resets the gap")
    func stepResetsGap() {
        let d = InactivityDetector(limitMs: 60_000)
        d.onStep(atMs: 0)
        d.onStep(atMs: 50_000)
        #expect(!d.isInactive(nowMs: 100_000))
        #expect(d.isInactive(nowMs: 110_000))
    }

    @Test("without any step reading it never fires")
    func neverFiresWithoutStep() {
        let d = InactivityDetector(limitMs: 60_000)
        #expect(!d.isInactive(nowMs: 1_000_000))
    }
}
