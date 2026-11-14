import Foundation
import HealthKit

// Conversions from the watch's Apple Health readings to the API's units (04 §3, ADR-008). Pure
// functions: the HealthKit queries live elsewhere.

/// HealthKit's blood oxygen is a fraction (0.97); the API wants whole percent.
func spo2Percent(_ fraction: Double) -> Int {
    Int((fraction * 100).rounded())
}

/// The API's classification string; `.notSet` and cases newer than this SDK are `unrecognized`.
func classificationName(_ c: HKElectrocardiogram.Classification) -> String {
    switch c {
    case .sinusRhythm: "sinus_rhythm"
    case .atrialFibrillation: "atrial_fibrillation"
    case .inconclusiveLowHeartRate: "inconclusive_low_heart_rate"
    case .inconclusiveHighHeartRate: "inconclusive_high_heart_rate"
    case .inconclusivePoorReading: "inconclusive_poor_reading"
    case .inconclusiveOther: "inconclusive_other"
    case .unrecognized, .notSet: "unrecognized"
    @unknown default: "unrecognized"
    }
}

/// The first `seconds` of an ECG, averaged down to about `targetHz` and in microvolts (clamped to
/// ±10 mV), so the trace stays small enough to post. Nil when there is nothing to send.
func shortenTrace(
    volts: [Double], hz: Double, seconds: Double = 10, targetHz: Double = 128
) -> (trace: [Int], hz: Int)? {
    guard !volts.isEmpty, hz > 0 else { return nil }
    let factor = max(1, Int((hz / targetHz).rounded()))
    let head = volts.prefix(Int(hz * seconds))
    let trace = stride(from: 0, to: head.count - factor + 1, by: factor).map { start in
        let mean = head.dropFirst(start).prefix(factor).reduce(0, +) / Double(factor)
        return Int(max(-10_000, min(10_000, (mean * 1_000_000).rounded())))
    }
    return (trace, Int((hz / Double(factor)).rounded()))
}

/// ISO-8601 with fractional seconds, as the watch's events carry.
func healthTimestamp(_ date: Date) -> String {
    Date.ISO8601FormatStyle(includingFractionalSeconds: true).format(date)
}
