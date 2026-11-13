package ro.echocare.shared

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PulseAnomalyTest {
    @Test
    fun `fires once pulse stays high at rest past the hold window`() {
        val a = PulseAnomaly(marginBpm = 25, holdMs = 60_000L)
        // One minute at 100 bpm with a 70 bpm baseline, still
        var fired = false
        for (t in 0L..60_000L step 1_000L) {
            fired =
                a.onReading(t, bpm = 100, baselineBpm = 70, moving = false)
        }
        assertTrue(fired)
    }

    @Test
    fun `no anomaly before the resting baseline is measured`() {
        val a = PulseAnomaly(marginBpm = 25, holdMs = 60_000L)
        var fired = false
        for (t in 0L..120_000L step 1_000L) {
            fired = fired || a.onReading(t, bpm = 140, baselineBpm = null, moving = false)
        }
        assertFalse(fired)
    }

    @Test
    fun `a brief spike that returns to baseline is not an anomaly`() {
        val a = PulseAnomaly(marginBpm = 25, holdMs = 60_000L)
        a.onReading(0L, bpm = 100, baselineBpm = 70, moving = false)
        val fired = a.onReading(30_000L, bpm = 72, baselineBpm = 70, moving = false)
        assertFalse(fired)
    }

    @Test
    fun `high pulse while moving is not an anomaly`() {
        val a = PulseAnomaly(marginBpm = 25, holdMs = 60_000L)
        var fired = false
        for (t in 0L..120_000L step 1_000L) {
            fired =
                a.onReading(t, bpm = 150, baselineBpm = 70, moving = true)
        }
        assertFalse(fired)
    }

    @Test
    fun `at the baseline plus margin minus one it does not fire`() {
        val a = PulseAnomaly(marginBpm = 25, holdMs = 60_000L)
        var fired = false
        for (t in 0L..120_000L step 1_000L) {
            fired =
                a.onReading(t, bpm = 94, baselineBpm = 70, moving = false)
        }
        assertFalse(fired)
    }
}
