package ro.echocare.push

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import ro.echocare.shared.CheckInMessage
import ro.echocare.shared.EventMessage
import ro.echocare.shared.EventSnapshot

class WearListenerServiceTest {
    @Test
    fun `event with snapshot maps to EventForm with source = watch`() {
        val msg = EventMessage(
            id = "6569b60e-fdf8-4dfe-916d-025f5e573186",
            type = "high_pulse_at_rest",
            measuredAt = "2026-11-12T19:00:00Z",
            snapshot = EventSnapshot(
                pulse = 125,
                restingBaseline = 70,
                moving = false,
                minutesWithoutSteps = 0,
                battery = 55
            )
        )
        val form = msg.toEventForm()
        assertEquals("6569b60e-fdf8-4dfe-916d-025f5e573186", form.id)
        assertEquals("high_pulse_at_rest", form.type)
        assertEquals("2026-11-12T19:00:00Z", form.measuredAt)
        assertEquals("watch", form.source)
        assertEquals(125, form.snapshot?.pulse)
        assertEquals(70, form.snapshot?.restingBaseline)
    }

    @Test
    fun `event with empty snapshot maps to EventForm without snapshot`() {
        val msg = EventMessage(id = "a", type = "manual_request", measuredAt = "t")
        val form = msg.toEventForm()
        assertEquals("watch", form.source)
        assertNull(form.snapshot)
    }

    @Test
    fun `check-in maps every field through`() {
        val msg = CheckInMessage(
            measuredAt = "2026-11-12T19:00:00Z",
            battery = 42,
            worn = false,
            lastPulse = 88
        )
        val form = msg.toCheckInForm()
        assertEquals("2026-11-12T19:00:00Z", form.measuredAt)
        assertEquals(42, form.battery)
        assertEquals(false, form.worn)
        assertEquals(88, form.lastPulse)
    }
}
