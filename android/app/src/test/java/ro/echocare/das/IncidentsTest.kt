package ro.echocare.das

import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.IncidentRow

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
}
