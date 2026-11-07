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
            lastPulse = 88
        )
        val decoded = CheckInMessage.fromBytes(original.toBytes())
        assertEquals(original, decoded)
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
}
