import Testing
@testable import Shared

struct PulseAnomalyTests {
    @Test("fires once pulse stays high at rest past the hold window")
    func firesAfterHold() {
        let a = PulseAnomaly(marginBpm: 25, holdMs: 60_000)
        // One minute at 100 bpm with a 70 bpm baseline, still
        var fired = false
        for t in stride(from: Int64(0), through: 60_000, by: 1_000) {
            fired = a.onReading(atMs: t, bpm: 100, baselineBpm: 70, moving: false)
        }
        #expect(fired)
    }

    @Test("no anomaly before the resting baseline is measured")
    func noBaselineNoAnomaly() {
        let a = PulseAnomaly(marginBpm: 25, holdMs: 60_000)
        var fired = false
        for t in stride(from: Int64(0), through: 120_000, by: 1_000) {
            fired = fired || a.onReading(atMs: t, bpm: 140, baselineBpm: nil, moving: false)
        }
        #expect(!fired)
    }

    @Test("a brief spike that returns to baseline is not an anomaly")
    func briefSpike() {
        let a = PulseAnomaly(marginBpm: 25, holdMs: 60_000)
        _ = a.onReading(atMs: 0, bpm: 100, baselineBpm: 70, moving: false)
        let fired = a.onReading(atMs: 30_000, bpm: 72, baselineBpm: 70, moving: false)
        #expect(!fired)
    }

    @Test("high pulse while moving is not an anomaly")
    func highWhileMoving() {
        let a = PulseAnomaly(marginBpm: 25, holdMs: 60_000)
        var fired = false
        for t in stride(from: Int64(0), through: 120_000, by: 1_000) {
            fired = a.onReading(atMs: t, bpm: 150, baselineBpm: 70, moving: true)
        }
        #expect(!fired)
    }

    @Test("at the baseline plus margin minus one it does not fire")
    func justBelowMargin() {
        let a = PulseAnomaly(marginBpm: 25, holdMs: 60_000)
        var fired = false
        for t in stride(from: Int64(0), through: 120_000, by: 1_000) {
            fired = a.onReading(atMs: t, bpm: 94, baselineBpm: 70, moving: false)
        }
        #expect(!fired)
    }
}
