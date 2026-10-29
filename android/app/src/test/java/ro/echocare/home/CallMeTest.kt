package ro.echocare.home

import java.time.Instant
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import ro.echocare.EventResult

// UC-10, 04 §3: „Sunați-mă” posts a manual_request and shows what the server answered.
class CallMeTest {
    // The same settings as NetworkModule.
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun theRequestIsSentAsTheServerReadsIt() {
        val form = manualRequest("e1", Instant.parse("2026-10-29T20:00:00Z"))
        assertEquals(
            """{"id":"e1","type":"manual_request","measured_at":"2026-10-29T20:00:00Z"}""",
            json.encodeToString(form)
        )
    }

    @Test
    fun everyTapHasItsOwnId() {
        assertNotEquals(manualRequest().id, manualRequest().id)
    }

    @Test
    fun aCallIsComingOnlyWhenTheServerNamedOne() {
        assertEquals(
            CallMe.Coming,
            callMeAfter(Answer.Ok(EventResult(queued = true, callId = "c1")))
        )
        // A tap that joined the call already there
        assertEquals(
            CallMe.Coming,
            callMeAfter(Answer.Ok(EventResult(queued = false, callId = "c1")))
        )
        // Recorded, but stale or the senior is not active: no call
        assertEquals(CallMe.NotSent, callMeAfter(Answer.Ok(EventResult())))
    }

    @Test
    fun aFailedTapInvitesAnother() {
        for (failure in Failure.entries) {
            assertEquals(CallMe.NotSent, callMeAfter(Answer.No(failure)))
        }
    }

    @Test
    fun anAnswerMissingFieldsOrWithNewOnesIsDecoded() {
        assertEquals(EventResult(), json.decodeFromString<EventResult>("{}"))
        assertEquals(
            EventResult(queued = true, callId = "c1"),
            json.decodeFromString<EventResult>("""{"queued": true, "call_id": "c1", "later": 1}""")
        )
    }
}
