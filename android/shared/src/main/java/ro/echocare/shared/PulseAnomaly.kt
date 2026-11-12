package ro.echocare.shared

/**
 * High pulse at rest (UC-09 step 1, event type `high_pulse_at_rest`). A reading is anomalous when
 * the wearer is not moving and the pulse exceeds the resting baseline by at least [marginBpm].
 * The spec doesn't fix a multiplier (Q, open); this uses a flat margin and holds for [holdMs] so
 * one spurious spike doesn't start a call.
 */
class PulseAnomaly(private val marginBpm: Int = 25, private val holdMs: Long = 60_000L) {
    private var sinceMs = -1L

    /**
     * Feed every valid heart-rate reading with the wearer's current resting baseline. Returns
     * true the first time the pulse has stayed high at rest for at least [holdMs]; the caller
     * then clears the detector with [reset] once it has acted on the anomaly.
     */
    fun onReading(atMs: Long, bpm: Int, baselineBpm: Int, moving: Boolean): Boolean {
        val high = !moving && bpm > 0 && bpm >= baselineBpm + marginBpm
        if (!high) {
            sinceMs = -1L
            return false
        }
        if (sinceMs < 0) sinceMs = atMs
        return atMs - sinceMs >= holdMs
    }

    fun reset() {
        sinceMs = -1L
    }
}
