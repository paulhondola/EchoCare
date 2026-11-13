package ro.echocare.shared

import org.junit.Assert.assertEquals
import org.junit.Test

class WearMessageTest {
    @Test
    fun `check-in round-trips through bytes with every field set`() {
        val original = CheckInMessage(
            measuredAt = "2026-11-07T19:45:00Z",
            battery = 73,
            worn = true,
            lastPulse = 88,
            restingPulse = 66,
            stepsToday = 2450,
            minutesWithoutSteps = 14
        )
        val decoded = CheckInMessage.fromBytes(original.toBytes())
        assertEquals(original, decoded)
    }

    @Test
    fun `a check-in from an older watch decodes the added fields as null`() {
        val old = """{"measured_at":"2026-11-07T19:45:00Z",""" +
            """"battery":73,"worn":true,"last_pulse":88}"""
        val decoded = CheckInMessage.fromBytes(old.encodeToByteArray())
        assertEquals(CheckInMessage("2026-11-07T19:45:00Z", 73, true, 88), decoded)
    }

    @Test
    fun `check-in omits null fields and decodes them back as null`() {
        val original = CheckInMessage(
            measuredAt = "2026-11-07T19:45:00Z",
            battery = null,
            worn = false,
            lastPulse = null
        )
        val decoded = CheckInMessage.fromBytes(original.toBytes())
        assertEquals(original, decoded)
    }

    @Test
    fun `event round-trips through bytes`() {
        val original = EventMessage(
            id = "6569b60e-fdf8-4dfe-916d-025f5e573186",
            type = "fall",
            measuredAt = "2026-11-07T19:28:51.814+00:00"
        )
        val decoded = EventMessage.fromBytes(original.toBytes())
        assertEquals(original, decoded)
    }

    @Test
    fun `event round-trips with a full snapshot`() {
        val original = EventMessage(
            id = "6569b60e-fdf8-4dfe-916d-025f5e573186",
            type = "high_pulse_at_rest",
            measuredAt = "2026-11-07T19:28:51.814+00:00",
            snapshot = EventSnapshot(
                pulse = 120,
                restingBaseline = 72,
                moving = false,
                minutesWithoutSteps = 0,
                battery = 55
            )
        )
        val decoded = EventMessage.fromBytes(original.toBytes())
        assertEquals(original, decoded)
    }

    @Test
    fun `an event with no snapshot serialises without one`() {
        val msg = EventMessage(
            id = "a",
            type = "manual_request",
            measuredAt = "t"
        )
        val encoded = msg.toBytes().decodeToString()
        assertEquals(false, encoded.contains("snapshot"))
    }
}
