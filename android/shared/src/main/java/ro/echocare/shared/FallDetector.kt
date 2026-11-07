package ro.echocare.shared

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Detects a fall from the watch's accelerometer (P19, UC-09): an impact above [impactG], then
 * [stillMs] within [stillToleranceG] of 1 g. Free fall is not required: at the wrist it is often
 * missing in a real fall and present in ordinary movement. Thresholds from spike S13
 * (docs/specs/echocare/spike-results.md).
 *
 * Feed it every accelerometer reading in order. It returns true once per detected fall; the
 * watch then asks „Sunteți bine?", which also catches sitting down hard or lying down quickly.
 */
class FallDetector(
    private val impactG: Float = 2f,
    private val stillMs: Long = 7_000,
    private val stillToleranceG: Float = 0.1f,
    // Assumed, not measured in S13: how long after the impact the stillness may begin, to let the body settle
    private val settleMs: Long = 5_000
) {
    private var impactAtMs = -1L
    private var stillSinceMs = -1L

    fun onReading(timestampMs: Long, g: Float): Boolean {
        if (g > impactG) {
            // A later, or bouncing, impact starts the wait over
            impactAtMs = timestampMs
            stillSinceMs = -1L
            return false
        }
        if (impactAtMs < 0) return false

        if (abs(g - 1f) >= stillToleranceG) {
            stillSinceMs = -1L
            if (timestampMs - impactAtMs > settleMs) impactAtMs = -1L
            return false
        }
        if (stillSinceMs < 0) {
            if (timestampMs - impactAtMs > settleMs) {
                impactAtMs = -1L
                return false
            }
            stillSinceMs = timestampMs
        }
        if (timestampMs - stillSinceMs < stillMs) return false

        impactAtMs = -1L
        stillSinceMs = -1L
        return true
    }

    companion object {
        private const val STANDARD_GRAVITY = 9.80665f

        /** The total acceleration in g, from the three axes in m/s². */
        fun accelerationG(x: Float, y: Float, z: Float): Float =
            sqrt(x * x + y * y + z * z) / STANDARD_GRAVITY
    }
}
