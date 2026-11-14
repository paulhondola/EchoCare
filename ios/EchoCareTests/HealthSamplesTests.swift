import HealthKit
import Testing

@testable import EchoCare

struct HealthSamplesTests {
    @Test func spo2RoundsToAPercent() {
        #expect(spo2Percent(0.974) == 97)
        #expect(spo2Percent(0.976) == 98)
    }

    @Test func everyClassificationHasItsName() {
        #expect(classificationName(.sinusRhythm) == "sinus_rhythm")
        #expect(classificationName(.atrialFibrillation) == "atrial_fibrillation")
        #expect(classificationName(.inconclusiveLowHeartRate) == "inconclusive_low_heart_rate")
        #expect(classificationName(.inconclusiveHighHeartRate) == "inconclusive_high_heart_rate")
        #expect(classificationName(.inconclusivePoorReading) == "inconclusive_poor_reading")
        #expect(classificationName(.inconclusiveOther) == "inconclusive_other")
        #expect(classificationName(.unrecognized) == "unrecognized")
        #expect(classificationName(.notSet) == "unrecognized")
    }

    @Test func shortens512HzTo128HzForTenSeconds() {
        let volts = Array(repeating: 0.000_5, count: 512 * 30)
        let r = shortenTrace(volts: volts, hz: 512)!
        #expect(r.hz == 128)
        #expect(r.trace.count == 1_280)
        #expect(r.trace.allSatisfy { $0 == 500 })
    }

    @Test func averagesEachGroup() {
        let r = shortenTrace(
            volts: [0.000_001, 0.000_002, 0.000_003, 0.000_006], hz: 512, seconds: 1)!
        #expect(r.trace == [3])
    }

    @Test func clampsToTenMillivolts() {
        #expect(shortenTrace(volts: [0.02, -0.02], hz: 128)!.trace == [10_000, -10_000])
    }

    @Test func shortensAnyRate() {
        let r = shortenTrace(volts: Array(repeating: 0, count: 2_560), hz: 256)!
        #expect(r.hz == 128)
        #expect(r.trace.count == 1_280)
    }

    @Test func emptyVoltagesGiveNoTrace() {
        #expect(shortenTrace(volts: [], hz: 512) == nil)
    }
}
