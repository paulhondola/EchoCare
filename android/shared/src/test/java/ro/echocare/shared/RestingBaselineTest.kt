package ro.echocare.shared

import org.junit.Assert.assertEquals
import org.junit.Test

class RestingBaselineTest {
    @Test
    fun `defaults to the bootstrap value before enough still readings land`() {
        val b = RestingBaseline(minSamples = 10, defaultBpm = 70)
        repeat(5) { b.onReading(it * 1_000L, bpm = 80, moving = false) }
        assertEquals(70, b.value(5_000L))
    }

    @Test
    fun `measured is null until enough still readings land, then the mean`() {
        val b = RestingBaseline(minSamples = 10, defaultBpm = 70)
        repeat(9) { b.onReading(it * 1_000L, bpm = 62, moving = false) }
        assertEquals(null, b.measured(9_000L))
        b.onReading(9_000L, bpm = 62, moving = false)
        assertEquals(62, b.measured(10_000L))
    }

    @Test
    fun `averages still readings once the window has enough`() {
        val b = RestingBaseline(minSamples = 10, defaultBpm = 70)
        repeat(10) { b.onReading(it * 1_000L, bpm = 60, moving = false) }
        assertEquals(60, b.value(10_000L))
    }

    @Test
    fun `ignores readings while the wearer is moving`() {
        val b = RestingBaseline(minSamples = 10, defaultBpm = 70)
        repeat(10) { b.onReading(it * 1_000L, bpm = 150, moving = true) }
        assertEquals(70, b.value(10_000L))
    }

    @Test
    fun `old samples drop out of the rolling window`() {
        val b = RestingBaseline(windowMs = 60_000L, minSamples = 5, defaultBpm = 70)
        repeat(10) { b.onReading(it * 1_000L, bpm = 100, moving = false) }
        // 70 seconds later only the newer readings should remain; none are added, so the baseline
        // falls back to default since fewer than minSamples survive
        assertEquals(70, b.value(70_001L))
    }
}
