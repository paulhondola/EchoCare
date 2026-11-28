package ro.echocare.wear.monitoring

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AlertTest {
    private val alert = Alert(id = "a", sentAtMs = 1_000)

    @Test
    fun `sending, then retrying after 20 s, and only then dismissable`() {
        assertEquals(HelpPhase.SENDING, alert.phase(1_000 + HELP_RETRYING_MS - 1))
        assertFalse(alert.canDismiss(1_000 + HELP_RETRYING_MS - 1))
        assertEquals(HelpPhase.RETRYING, alert.phase(1_000 + HELP_RETRYING_MS))
        assertTrue(alert.canDismiss(1_000 + HELP_RETRYING_MS))
    }

    @Test
    fun `only the matching ack marks it received`() {
        assertEquals(alert, alert.acked("old", 2_000))
        val received = alert.acked("a", 2_000)
        assertEquals(HelpPhase.RECEIVED, received.phase(2_000))
        assertTrue(received.canDismiss(2_000))
        // A resent duplicate keeps the first time
        assertEquals(received, received.acked("a", 9_000))
    }
}
