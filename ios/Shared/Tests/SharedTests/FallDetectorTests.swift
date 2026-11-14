import Testing
@testable import Shared

private let armSwing: [Float] = [0.6, 1.6]

// Synthetic traces at the watch's 50 readings a second, shaped after the S13 trials (spike-results.md)
struct FallDetectorTests {
    private let periodMs: Int64 = 20

    private struct Trace {
        var readings: [Float] = []

        mutating func hold(_ g: Float, ms: Int64) {
            readings.append(contentsOf: Array(repeating: g, count: Int(ms / 20)))
        }

        mutating func impact(_ g: Float) {
            readings.append(g)
        }

        // Arm movement, alternating around 1 g by more than the stillness tolerance
        mutating func move(ms: Int64) {
            for i in 0..<Int(ms / 20) { readings.append(armSwing[i % 2]) }
        }
    }

    private func detections(_ build: (inout Trace) -> Void) -> Int {
        let detector = FallDetector()
        var trace = Trace()
        build(&trace)
        var count = 0
        for (i, g) in trace.readings.enumerated() {
            if detector.onReading(timestampMs: Int64(i) * periodMs, g: g) { count += 1 }
        }
        return count
    }

    @Test("a fall with a strong impact, then stillness, is detected once")
    func strongImpact() {
        #expect(
            detections {
                $0.hold(1, ms: 1_000)
                $0.impact(8.3)
                $0.move(ms: 1_500)
                $0.hold(1, ms: 15_000)
            } == 1)
    }

    @Test("a soft fall backwards onto a bed is detected")
    func softFall() {
        #expect(
            detections {
                $0.hold(1, ms: 1_000)
                $0.impact(2.04)
                $0.move(ms: 1_000)
                $0.hold(1.02, ms: 10_000)
            } == 1)
    }

    @Test("a slap on a table, with the arm moving on, is not a fall")
    func slapOnTable() {
        #expect(
            detections {
                $0.hold(1, ms: 1_000)
                $0.impact(11.8)
                $0.move(ms: 15_000)
            } == 0)
    }

    @Test("walking with a peak below the impact threshold is not a fall")
    func walking() {
        #expect(
            detections {
                for _ in 0..<10 {
                    $0.impact(1.9)
                    $0.move(ms: 500)
                }
                $0.hold(1, ms: 10_000)
            } == 0)
    }

    @Test("stillness shorter than seven seconds is not a fall")
    func shortStillness() {
        #expect(
            detections {
                $0.impact(5)
                $0.hold(1, ms: 6_000)
                $0.move(ms: 5_000)
            } == 0)
    }

    @Test("stillness that begins long after the impact is not a fall")
    func lateStillness() {
        #expect(
            detections {
                $0.impact(5)
                $0.move(ms: 6_000)
                $0.hold(1, ms: 10_000)
            } == 0)
    }

    @Test("sitting down hard matches, and the wrist prompt is what catches it")
    func sittingDownHard() {
        #expect(
            detections {
                $0.impact(2.74)
                $0.hold(1, ms: 10_000)
            } == 1)
    }

    @Test("acceleration at rest is one g")
    func accelerationAtRest() {
        let g = FallDetector.accelerationG(x: 0, y: 0, z: 9.80665)
        #expect(abs(g - 1) < 0.001)
    }
}
