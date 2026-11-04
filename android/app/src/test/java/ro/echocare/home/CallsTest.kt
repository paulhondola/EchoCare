package ro.echocare.home

import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.CallRow
import ro.echocare.Medic
import ro.echocare.R
import ro.echocare.SeniorPage
import ro.echocare.ui.Tone

// UC-12: what the caregiver's page shows for each code and each call.
class CallsTest {
    private fun call(
        state: String = "completed",
        severity: String? = null,
        due: String = "2026-11-04T08:00:00Z",
        started: String? = null,
        ended: String? = null
    ) = CallRow(
        id = "c",
        trigger = "campaign",
        state = state,
        dueAt = due,
        startedAt = started,
        endedAt = ended,
        finalSeverity = severity
    )

    private fun senior(code: String?, live: Boolean?) = SeniorPage(
        id = "s",
        fullName = "Maria Pop",
        formOfAddress = "doamna Maria",
        phone = "+40700000101",
        landline = false,
        state = "active",
        code = code,
        reason = "Se simte rău",
        medic = Medic("Dr. Pop"),
        callInProgress = live
    )

    @Test
    fun eachCodeHasItsLabelAndColour() {
        assertEquals(R.string.code_green, CODE_LABELS["green"])
        assertEquals(R.string.code_yellow, CODE_LABELS["yellow"])
        assertEquals(R.string.code_red, CODE_LABELS["red"])
        assertEquals(Tone.Verde, CODE_TONES["green"])
        assertEquals(Tone.Galben, CODE_TONES["yellow"])
        assertEquals(Tone.Rosu, CODE_TONES["red"])
    }

    @Test
    fun noCodeOrAnUnknownOneShowsNoChip() {
        // Null before the first result and for a senior not active (04 §1)
        assertNull(CODE_LABELS[senior(null, null).code])
        assertNull(CODE_LABELS["purple"])
    }

    @Test
    fun aWatchThatIsNotWatchingIsAWarning() {
        // UC-13: a device warning beside the senior, not a code
        assertEquals(R.string.watch_not_worn to Tone.Galben, watchChip("not_worn"))
        assertEquals(R.string.watch_offline to Tone.Galben, watchChip("offline"))
    }

    @Test
    fun aWatchThatWorksIsNoWarning() {
        assertEquals(R.string.watch_ok to Tone.Muted, watchChip("ok"))
    }

    @Test
    fun noWatchOrAnUnknownStateShowsNoChip() {
        // Null for DAS and the senior, and before the first check-in (04 §1)
        assertNull(watchChip(null))
        assertNull(watchChip("charging"))
    }

    @Test
    fun anEndedCallShowsItsCode() {
        for (code in listOf("green", "yellow", "red")) {
            assertEquals(Outcome.Code(code), outcome(call(severity = code)))
        }
    }

    @Test
    fun aCallWithoutACodeShowsItsState() {
        assertEquals(Outcome.State("queued"), outcome(call(state = "queued")))
        assertEquals(Outcome.State("ringing"), outcome(call(state = "ringing")))
        assertEquals(Outcome.State("failed"), outcome(call(state = "failed")))
    }

    @Test
    fun aCodeThisBuildDoesNotKnowShowsTheState() {
        assertEquals(Outcome.State("completed"), outcome(call(severity = "purple")))
    }

    @Test
    fun aLiveCallStandsOut() {
        assertEquals(Tone.Galben, stateTone("ringing"))
        assertEquals(Tone.Galben, stateTone("in_progress"))
        assertEquals(Tone.Muted, stateTone("queued"))
        assertEquals(Tone.Muted, stateTone("unanswered"))
    }

    @Test
    fun theHistoryIsShortAndLeavesOutCanceledCalls() {
        val calls = listOf(call(state = "canceled")) + List(7) { call() }
        val recent = recentCalls(calls)
        assertEquals(RECENT_CALLS, recent.size)
        assertTrue(recent.none { it.state == "canceled" })
    }

    @Test
    fun aCallIsTimedByItsEndThenItsStartThenWhenItIsDue() {
        val utc = ZoneId.of("UTC")
        assertEquals("04.11 08:00", callTime(call(), utc))
        assertEquals("04.11 08:01", callTime(call(started = "2026-11-04T08:01:00Z"), utc))
        assertEquals(
            "04.11 08:05",
            callTime(call(started = "2026-11-04T08:01:00Z", ended = "2026-11-04T08:05:00Z"), utc)
        )
        // In the phone's zone: Bucharest is UTC+2 in November
        assertEquals("04.11 10:00", callTime(call(), ZoneId.of("Europe/Bucharest")))
    }

    @Test
    fun theBadgeShowsOnlyWhileACallIsLive() {
        assertTrue(showsCallBadge(senior("yellow", live = true)))
        assertFalse(showsCallBadge(senior("yellow", live = false)))
        // An older API that does not send the field
        assertFalse(showsCallBadge(senior("yellow", live = null)))
    }
}
