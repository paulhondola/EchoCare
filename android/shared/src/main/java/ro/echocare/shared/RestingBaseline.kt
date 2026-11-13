package ro.echocare.shared

/**
 * The wearer's resting pulse, tracked as a rolling mean of still-moment readings (UC-09 step 1).
 * Only readings reported while the wearer is not moving contribute, so a run at 150 bpm doesn't
 * push the baseline up. Starts [defaultBpm] until at least [minSamples] still readings land; from
 * then on a reading flags as anomalous when it stays above the baseline by a wide margin while not
 * moving.
 */
class RestingBaseline(
    private val windowMs: Long = 60 * 60_000L,
    private val minSamples: Int = 10,
    private val defaultBpm: Int = 70
) {
    private val samples = ArrayDeque<Sample>()
    private data class Sample(val atMs: Long, val bpm: Int)

    /** Call for every valid heart-rate reading. Non-still readings are ignored. */
    fun onReading(atMs: Long, bpm: Int, moving: Boolean) {
        if (!moving && bpm > 0) samples.addLast(Sample(atMs, bpm))
        drop(atMs)
    }

    /** The mean of still readings in the window, or [defaultBpm] before enough have landed. */
    fun value(nowMs: Long): Int = measured(nowMs) ?: defaultBpm

    /** The mean of still readings in the window, or null before enough have landed: what the check-in reports (ADR-006). */
    fun measured(nowMs: Long): Int? {
        drop(nowMs)
        if (samples.size < minSamples) return null
        return (samples.sumOf { it.bpm } / samples.size).coerceAtLeast(1)
    }

    private fun drop(nowMs: Long) {
        val cutoff = nowMs - windowMs
        while (samples.isNotEmpty() && samples.first().atMs < cutoff) samples.removeFirst()
    }
}
