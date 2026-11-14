package ro.echocare.home

import org.junit.Assert.assertEquals
import org.junit.Test
import ro.echocare.SeniorRow

// The medic home's to-do list (design 2026-11-13 medic home): which rows are tasks, in what order.
class TasksTest {
    private fun row(
        id: String,
        state: String,
        medical: String? = null,
        createdAt: String? = null,
        acceptedAt: String? = null
    ) = SeniorRow(
        id = id,
        fullName = id,
        formOfAddress = "Dna",
        phone = "+40700000000",
        landline = false,
        state = state,
        createdAt = createdAt,
        acceptedAt = acceptedAt,
        medicalRecordState = medical
    )

    @Test
    fun ordersByImportance() {
        val rows = listOf(
            row("d", "draft"),
            row("u", "unreachable"),
            row("w", "wrong_number"),
            row("f", "active", medical = "failed"),
            row("c", "active", medical = "review")
        )
        assertEquals(listOf("c", "f", "w", "u", "d"), tasksOf(rows).map { it.row.id })
    }

    @Test
    fun oneTaskPerSeniorTheMostImportant() {
        val tasks = tasksOf(listOf(row("a", "wrong_number", medical = "review")))
        assertEquals(listOf(MedicTask(tasks[0].row, TaskKind.Confirm)), tasks)
    }

    @Test
    fun noTaskForUnknownOrSettledValues() {
        val rows = listOf(
            row("x", "active", medical = "archived"),
            row("y", "withdrawn", medical = "review"),
            row("z", "refused", medical = "failed"),
            row("q", "someday", medical = "review"),
            row("g", "active", medical = "confirmed"),
            row("p", "accepted", medical = "pending"),
            row("s", "submitted")
        )
        assertEquals(emptyList<MedicTask>(), tasksOf(rows))
    }

    @Test
    fun oldestFirstWithinAKindNullTimesLast() {
        val rows = listOf(
            row("new", "draft", createdAt = "2026-11-12T10:00:00Z"),
            row("none", "draft"),
            row("old", "draft", createdAt = "2026-11-10T10:00:00Z")
        )
        assertEquals(listOf("old", "new", "none"), tasksOf(rows).map { it.row.id })
    }

    @Test
    fun welcomeCallProblemsOldestAcceptedFirst() {
        val rows = listOf(
            row("late", "unreachable", acceptedAt = "2026-11-12T10:00:00Z"),
            row("early", "unreachable", acceptedAt = "2026-11-09T10:00:00Z")
        )
        assertEquals(listOf("early", "late"), tasksOf(rows).map { it.row.id })
    }
}
