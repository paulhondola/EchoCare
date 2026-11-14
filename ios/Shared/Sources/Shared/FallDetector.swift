/// Detects a fall from the watch's accelerometer (P19, UC-09): an impact above `impactG`, then
/// `stillMs` within `stillToleranceG` of 1 g. Free fall is not required: at the wrist it is often
/// missing in a real fall and present in ordinary movement. Thresholds from spike S13
/// (docs/specs/echocare/spike-results.md).
///
/// Feed it every accelerometer reading in order. It returns true once per detected fall; the
/// watch then asks „Sunteți bine?", which also catches sitting down hard or lying down quickly.
public final class FallDetector {
    private let impactG: Float
    private let stillMs: Int64
    private let stillToleranceG: Float
    // Assumed, not measured in S13: how long after the impact the stillness may begin, to let the body settle
    private let settleMs: Int64
    private var impactAtMs: Int64 = -1
    private var stillSinceMs: Int64 = -1

    public init(
        impactG: Float = 2,
        stillMs: Int64 = 7_000,
        stillToleranceG: Float = 0.1,
        settleMs: Int64 = 5_000
    ) {
        self.impactG = impactG
        self.stillMs = stillMs
        self.stillToleranceG = stillToleranceG
        self.settleMs = settleMs
    }

    public func onReading(timestampMs: Int64, g: Float) -> Bool {
        if g > impactG {
            // A later, or bouncing, impact starts the wait over
            impactAtMs = timestampMs
            stillSinceMs = -1
            return false
        }
        if impactAtMs < 0 { return false }

        if abs(g - 1) >= stillToleranceG {
            stillSinceMs = -1
            if timestampMs - impactAtMs > settleMs { impactAtMs = -1 }
            return false
        }
        if stillSinceMs < 0 {
            if timestampMs - impactAtMs > settleMs {
                impactAtMs = -1
                return false
            }
            stillSinceMs = timestampMs
        }
        if timestampMs - stillSinceMs < stillMs { return false }

        impactAtMs = -1
        stillSinceMs = -1
        return true
    }

    private static let standardGravity: Float = 9.80665

    /// The total acceleration in g, from the three axes in m/s². CoreMotion already reports in g,
    /// so the watch doesn't need this; it is kept for parity with Android.
    public static func accelerationG(x: Float, y: Float, z: Float) -> Float {
        (x * x + y * y + z * z).squareRoot() / standardGravity
    }
}
