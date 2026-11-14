import Testing
@testable import Shared

struct RestingBaselineTests {
    @Test("defaults to the bootstrap value before enough still readings land")
    func defaultsBeforeEnough() {
        let b = RestingBaseline(minSamples: 10, defaultBpm: 70)
        for i in 0..<5 { b.onReading(atMs: Int64(i) * 1_000, bpm: 80, moving: false) }
        #expect(b.value(nowMs: 5_000) == 70)
    }

    @Test("measured is null until enough still readings land, then the mean")
    func measuredNilThenMean() {
        let b = RestingBaseline(minSamples: 10, defaultBpm: 70)
        for i in 0..<9 { b.onReading(atMs: Int64(i) * 1_000, bpm: 62, moving: false) }
        #expect(b.measured(nowMs: 9_000) == nil)
        b.onReading(atMs: 9_000, bpm: 62, moving: false)
        #expect(b.measured(nowMs: 10_000) == 62)
    }

    @Test("averages still readings once the window has enough")
    func averagesStill() {
        let b = RestingBaseline(minSamples: 10, defaultBpm: 70)
        for i in 0..<10 { b.onReading(atMs: Int64(i) * 1_000, bpm: 60, moving: false) }
        #expect(b.value(nowMs: 10_000) == 60)
    }

    @Test("ignores readings while the wearer is moving")
    func ignoresMoving() {
        let b = RestingBaseline(minSamples: 10, defaultBpm: 70)
        for i in 0..<10 { b.onReading(atMs: Int64(i) * 1_000, bpm: 150, moving: true) }
        #expect(b.value(nowMs: 10_000) == 70)
    }

    @Test("old samples drop out of the rolling window")
    func oldSamplesDrop() {
        let b = RestingBaseline(windowMs: 60_000, minSamples: 5, defaultBpm: 70)
        for i in 0..<10 { b.onReading(atMs: Int64(i) * 1_000, bpm: 100, moving: false) }
        // 70 seconds later only the newer readings should remain; none are added, so the baseline
        // falls back to default since fewer than minSamples survive
        #expect(b.value(nowMs: 70_001) == 70)
    }
}
