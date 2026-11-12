package ro.echocare.shared

/**
 * No steps for long enough during an active warning (UC-09 step 1, event type `inactivity`). The
 * spec limit is 4 h normally, 60 s in a demo (06 §3). The caller feeds every step reading and
 * polls [isInactive] on a timer; it fires once per gap and the caller clears it with [reset] when
 * it has acted.
 */
class InactivityDetector(private val limitMs: Long = 4 * 60 * 60_000L) {
    private var lastStepAtMs = -1L
    private var fired = false

    fun onStep(atMs: Long) {
        lastStepAtMs = atMs
        fired = false
    }

    /** True once when the gap has first exceeded [limitMs]. */
    fun isInactive(nowMs: Long): Boolean {
        if (fired || lastStepAtMs < 0) return false
        if (nowMs - lastStepAtMs < limitMs) return false
        fired = true
        return true
    }

    fun reset() {
        fired = false
        lastStepAtMs = -1L
    }
}
