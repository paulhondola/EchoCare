package ro.echocare.das

import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.CallReport
import ro.echocare.CallTurn
import ro.echocare.IncidentCall
import ro.echocare.IncidentRow
import ro.echocare.IncidentSenior
import ro.echocare.R
import ro.echocare.TriggerEvent
import ro.echocare.enroll.Refusal
import ro.echocare.home.Failure

// UC-12, design §"The list": what the DAS home shows, in which order.
class IncidentsTest {
    private val now = Instant.parse("2026-10-22T20:00:00Z")

    private fun row(id: String, status: String, openedAt: String, takenAt: String? = null) =
        IncidentRow(
            id = id,
            seniorName = "Dumitru Pop",
            formOfAddress = "domnul Dumitru",
            status = status,
            reason = "Durere în piept",
            openedAt = "2026-10-22T$openedAt:00Z",
            takenByName = takenAt?.let { "DAS Test" },
            takenAt = takenAt?.let { "2026-10-22T$it:00Z" }
        )

    @Test
    fun openComeFirstOldestFirst() {
        val rows = listOf("19:15", "19:06", "18:29").map { row(it, "open", it) }
        assertEquals(listOf("18:29", "19:06", "19:15"), sections(rows).open.map { it.id })
    }

    @Test
    fun inProgressSortsByTakeTimeThenOpenTime() {
        val rows = listOf(
            row("A", "in_progress", "18:00", takenAt = "19:00"),
            // No take time: the open time stands in
            row("B", "in_progress", "18:30")
        )
        assertEquals(listOf("B", "A"), sections(rows).inProgress.map { it.id })
    }

    @Test
    fun unknownStatusIsLeftOut() {
        val s = sections(listOf(row("R", "resolved", "18:00"), row("X", "archived", "18:00")))
        assertTrue(s.open.isEmpty())
        assertTrue(s.inProgress.isEmpty())
    }

    @Test
    fun agoBoundaries() {
        fun before(seconds: Long) = now.minusSeconds(seconds).toString()
        assertEquals(Ago.Moments, ago(before(30), now))
        assertEquals(Ago.Minutes(59), ago(before(59 * 60), now))
        assertEquals(Ago.Hours(1, 0), ago(before(60 * 60), now))
        assertEquals(Ago.Hours(23, 59), ago(before((23 * 60 + 59) * 60L), now))
        assertEquals(Ago.On(now.minusSeconds(24 * 3600)), ago(before(24 * 3600), now))
        // A phone clock behind the server's: never "in the future"
        assertEquals(Ago.Moments, ago(now.plusSeconds(90).toString(), now))
    }

    @Test
    fun agoReadsFastApiTimestamps() {
        assertEquals(Ago.Minutes(53), ago("2026-10-22T19:06:55.123456+00:00", now))
    }

    // design §"The incident page"

    private fun at(hm: String) = "2026-10-22T$hm:00Z"

    private fun report(severity: String, quote: String?, hm: String) =
        CallReport(severity = severity, reason = "R $hm", quote = quote, at = at(hm))

    private fun turn(hm: String) = CallTurn(speaker = "senior", content = "T $hm", at = at(hm))

    private fun call(
        id: String = "c",
        state: String = "completed",
        startedAt: String? = null,
        reports: List<CallReport> = emptyList(),
        turns: List<CallTurn> = emptyList()
    ) = IncidentCall(
        id = id,
        trigger = "campaign",
        attempt = 1,
        state = state,
        startedAt = startedAt?.let(::at),
        reports = reports,
        turns = turns
    )

    private val street = IncidentSenior(
        id = "s",
        fullName = "Dumitru Pop",
        formOfAddress = "domnul Dumitru",
        phone = "+40700000113",
        landline = false,
        street = "Strada Bucovinei",
        streetNumber = "27"
    )

    @Test
    fun seniorsWordsIsTheLatestRedQuote() {
        val calls = listOf(
            call(
                "a",
                reports = listOf(report("yellow", "q1", "19:00"), report("red", "q2", "19:06"))
            ),
            call("b", reports = listOf(report("red", "q3", "19:20")))
        )
        assertEquals("q3", seniorsWords(calls))
    }

    @Test
    fun noRedQuoteMeansNoWords() {
        val calls = listOf(
            call(
                reports = listOf(
                    report("red", null, "19:00"),
                    report("red", "  ", "19:05"),
                    report("yellow", "q", "19:10")
                )
            )
        )
        assertNull(seniorsWords(calls))
        assertNull(seniorsWords(emptyList()))
    }

    @Test
    fun newestCallFirstIsTheApisOrderReversed() {
        // GET /incidents/{id} sends calls oldest first. An unanswered call never started, so
        // its start time cannot order it (seen with Ion Dumitrescu's redial in the seed).
        val calls = listOf(
            call("1", startedAt = "18:00"),
            call("2", state = "unanswered"),
            call("3", startedAt = "19:00")
        )
        assertEquals(listOf("3", "2", "1"), newestFirst(calls).map { it.id })
    }

    @Test
    fun liveWhenRingingOrInProgress() {
        assertTrue(callLive(listOf(call(state = "completed"), call(state = "ringing"))))
        assertTrue(callLive(listOf(call(state = "in_progress"))))
        assertFalse(callLive(listOf(call(state = "handed_over"), call(state = "unanswered"))))
    }

    @Test
    fun timelinePutsReportsWhereTheyHappened() {
        val flagged = report("red", "q", "19:41")
        val c =
            call(
                turns = listOf(turn("19:34"), turn("19:41"), turn("19:48")),
                reports = listOf(flagged)
            )
        assertEquals(
            listOf(
                Line.Said(turn("19:34")),
                Line.Said(turn("19:41")),
                Line.Flagged(flagged),
                Line.Said(turn("19:48"))
            ),
            timeline(c)
        )
    }

    @Test
    fun timelineOfACallWithNoTurns() {
        assertTrue(timeline(call()).isEmpty())
    }

    @Test
    fun mapsUsesCoordinatesWhenThereAreAny() {
        val event = TriggerEvent("sos_button", at("19:05"), latitude = 45.7489, longitude = 21.2087)
        assertEquals("geo:45.7489,21.2087?q=45.7489,21.2087", mapsUri(street, event))
    }

    @Test
    fun mapsFallsBackToTheAddress() {
        assertEquals(
            "geo:0,0?q=Strada%20Bucovinei%2027%2C%20Timi%C8%99oara",
            mapsUri(street, null)
        )
    }

    @Test
    fun noPlaceMeansNoMapsLink() {
        val nowhere = street.copy(street = null, streetNumber = null)
        assertNull(mapsUri(nowhere, TriggerEvent("fall", at("19:05"))))
    }

    // design §"Preiau", §"Rezolvare caz"

    @Test
    fun onlyOpenAndInProgressHaveAnAction() {
        assertEquals(Act.Take, actFor("open"))
        assertEquals(Act.Resolve, actFor("in_progress"))
        assertNull(actFor("resolved"))
        assertNull(actFor("archived"))
    }

    @Test
    fun takeRefusals() {
        assertEquals(
            Notice.TakenBy("Cristian Pavel"),
            noticeAfter(Refusal.AlreadyDone("Cristian Pavel"), Act.Take)
        )
        assertEquals(
            Notice.Says(R.string.incident_changed),
            noticeAfter(Refusal.AlreadyDone(null), Act.Take)
        )
        assertEquals(
            Notice.Says(R.string.incident_changed),
            noticeAfter(Refusal.WrongState, Act.Take)
        )
        assertEquals(
            Notice.Says(R.string.send_failed),
            noticeAfter(Refusal.Failed(Failure.NoConnection), Act.Take)
        )
        assertEquals(
            Notice.Says(R.string.not_allowed_action),
            noticeAfter(Refusal.Failed(Failure.NotAllowed), Act.Take)
        )
        assertEquals(
            Notice.Says(R.string.incident_gone),
            noticeAfter(Refusal.Failed(Failure.NotFound), Act.Take)
        )
        assertEquals(
            Notice.Ends(Failure.SignedOut),
            noticeAfter(Refusal.Failed(Failure.SignedOut), Act.Take)
        )
        assertEquals(
            Notice.Says(R.string.send_failed),
            noticeAfter(Refusal.Invalid(emptyList()), Act.Resolve)
        )
    }

    @Test
    fun resolveRefusals() {
        assertEquals(
            Notice.Says(R.string.already_resolved),
            noticeAfter(Refusal.AlreadyDone("X"), Act.Resolve)
        )
        assertEquals(
            Notice.Says(R.string.incident_changed),
            noticeAfter(Refusal.WrongState, Act.Resolve)
        )
    }

    @Test
    fun sendNeedsAnOutcomeAndANote() {
        assertFalse(canSend(null, "x"))
        assertFalse(canSend("team_sent", "   "))
        assertFalse(canSend("team_sent", "a".repeat(1001)))
        assertTrue(canSend("team_sent", "a".repeat(1000)))
    }

    @Test
    fun outcomesInTheDashboardsOrder() {
        assertEquals(
            listOf("senior_ok", "team_sent", "called_112", "not_reached", "false_alarm"),
            OUTCOMES.map { it.first }
        )
    }

    // Final review fixes

    @Test
    fun unknownAccuracyIsLeftOutNotZero() {
        val e = TriggerEvent("sos_button", at("19:05"), latitude = 45.7489, longitude = 21.2087)
        assertEquals(Location("45.7489", "21.2087", accuracy = null), location(e))
        assertEquals(14, location(e.copy(accuracy = 14.4))?.accuracy)
        assertNull(location(e.copy(latitude = null)))
    }

    @Test
    fun aNewerCallOpensWhenItArrives() {
        // The dispatcher opened the old call; a redial then joined the incident.
        val toggled = mapOf("old" to true)
        assertTrue(expanded("redial", newestId = "redial", toggled = toggled))
        assertTrue(expanded("old", newestId = "redial", toggled = toggled))
        assertFalse(expanded("other", newestId = "redial", toggled = toggled))
        // A newest call the dispatcher closed stays closed
        assertFalse(expanded("redial", newestId = "redial", toggled = mapOf("redial" to false)))
    }
}
