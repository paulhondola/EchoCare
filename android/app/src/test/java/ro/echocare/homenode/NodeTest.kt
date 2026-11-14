package ro.echocare.homenode

import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import ro.echocare.RoomInfo
import ro.echocare.home.roomTone
import ro.echocare.ui.Tone

class NodeTest {
    private val now = Instant.parse("2026-11-14T12:00:00Z")

    @Test
    fun aReadingIsTimedByThePhone() {
        val reading = parseReading(
            """{"temperature":14.2,"humidity":40,"seconds_since_motion":90,
               "seconds_since_start":600,"forecast_60m":12.5}"""
        )!!
        val form = reading.toForm(now)
        assertEquals("2026-11-14T12:00:00Z", form.measuredAt)
        assertEquals("2026-11-14T11:58:30Z", form.lastMotionAt)
        assertEquals(14.2, form.temperature, 0.0)
        assertEquals(12.5, form.forecast60m!!, 0.0)
    }

    @Test
    fun aReadingWithoutMotionSendsNoMotionTime() {
        assertNull(parseReading("""{"temperature":21}""")!!.toForm(now).lastMotionAt)
    }

    @Test
    fun somethingElseIsNotAReading() {
        assertNull(parseReading("{}"))
        assertNull(parseReading("not json"))
    }

    @Test
    fun anSosIsACallRequestFromTheHomeNode() {
        val form = parseSos("""{"id":"abc","seconds_ago":5,"via":"palm"}""")!!.toEventForm(now)
        assertEquals("abc", form.id)
        assertEquals("manual_request", form.type)
        assertEquals("home_node", form.source)
        assertEquals("2026-11-14T11:59:55Z", form.measuredAt)
    }

    @Test
    fun aFallCarriesTheScan() {
        val form = parseFall(
            """{"id":"f1","seconds_ago":2,"seconds_still":12,"object_angle_deg":105,
               "object_distance_m":2.1,"scan":[2.5,2.1,2.5]}"""
        )!!.toEventForm(now, latitude = 45.75)
        assertEquals("fall", form.type)
        assertEquals(listOf(2.5, 2.1, 2.5), form.snapshot!!.scan)
        assertEquals(105.0, form.snapshot!!.objectAngleDeg!!, 0.0)
        assertEquals(45.75, form.latitude!!, 0.0)
    }

    @Test
    fun theLightIsTheCodeOrACall() {
        assertEquals("call", lightFor("red", true))
        assertEquals("yellow", lightFor("yellow", false))
        assertEquals("green", lightFor(null, null))
        assertEquals("green", lightFor("purple", false))
    }

    @Test
    fun theBoxIsNamedByItsLastFourCharacters() {
        assertEquals("3F2A", boxLabel("AA:BB:CC:DD:3f:2a"))
    }

    @Test
    fun aRoomPastALimitOrASilentSensorIsYellow() {
        val room = RoomInfo(temperature = 14.0, roomState = "cold")
        assertEquals(Tone.Galben, roomTone(room))
        assertEquals(Tone.Galben, roomTone(room.copy(roomState = "ok", state = "offline")))
        assertEquals(Tone.Muted, roomTone(room.copy(roomState = "cold_soon")))
        assertEquals(Tone.Muted, roomTone(room.copy(temperature = 21.0, roomState = "ok")))
    }

    @Test
    fun theUuidsFollowTheSpike() {
        assertEquals("ec0f0000-7765-4f56-abaf-af4938f246ad", NodeUuids.SERVICE.toString())
        assertEquals("ec0f0007-7765-4f56-abaf-af4938f246ad", NodeUuids.ROOM_STATE.toString())
    }
}
