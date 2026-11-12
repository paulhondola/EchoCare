package ro.echocare.shared

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class InactivityDetectorTest {
    @Test
    fun `fires once when the gap first crosses the limit`() {
        val d = InactivityDetector(limitMs = 60_000L)
        d.onStep(0L)
        assertFalse(d.isInactive(59_000L))
        assertTrue(d.isInactive(60_000L))
    }

    @Test
    fun `does not fire twice without a reset`() {
        val d = InactivityDetector(limitMs = 60_000L)
        d.onStep(0L)
        assertTrue(d.isInactive(60_000L))
        assertFalse(d.isInactive(120_000L))
    }

    @Test
    fun `a step resets the gap`() {
        val d = InactivityDetector(limitMs = 60_000L)
        d.onStep(0L)
        d.onStep(50_000L)
        assertFalse(d.isInactive(100_000L))
        assertTrue(d.isInactive(110_000L))
    }

    @Test
    fun `without any step reading it never fires`() {
        val d = InactivityDetector(limitMs = 60_000L)
        assertFalse(d.isInactive(1_000_000L))
    }
}
