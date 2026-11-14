package ro.echocare.home

import java.time.Instant
import ro.echocare.SeniorRow

// The medic home's to-do list (design 2026-11-13 medic home): what only the medic can move,
// most important first. Plain Kotlin, tested on the JVM; built from the API's strings, never
// decoded, so a value this build does not know makes no task (ADR-001 §2.3).

/** The kinds of task, in their order of importance. */
enum class TaskKind { Confirm, AnalysisFailed, WrongNumber, Unreachable, Draft }

data class MedicTask(val row: SeniorRow, val kind: TaskKind)

// A refused or withdrawn senior, or one in a state this build does not know, needs no profile.
private fun wantsProfile(state: String) =
    state in STATE_LABELS && state !in setOf("refused", "withdrawn")

// One task per senior, the most important: a profile before a welcome-call problem.
private fun kindOf(row: SeniorRow): TaskKind? = when {
    row.medicalRecordState == "review" && wantsProfile(row.state) -> TaskKind.Confirm
    row.medicalRecordState == "failed" && wantsProfile(row.state) -> TaskKind.AnalysisFailed
    row.state == "wrong_number" -> TaskKind.WrongNumber
    row.state == "unreachable" -> TaskKind.Unreachable
    row.state == "draft" -> TaskKind.Draft
    else -> null
}

// How long it has waited: a draft since it was begun, a welcome-call problem since acceptance.
private fun waitingSince(task: MedicTask): Instant? = when (task.kind) {
    TaskKind.Draft -> instantOf(task.row.createdAt)
    TaskKind.WrongNumber, TaskKind.Unreachable -> instantOf(task.row.acceptedAt)
    else -> null
}

/** By kind, then the longest waiting first; no time last, otherwise the API's order. */
fun tasksOf(rows: List<SeniorRow>): List<MedicTask> = rows
    .mapNotNull { row -> kindOf(row)?.let { MedicTask(row, it) } }
    .sortedWith(
        compareBy<MedicTask> { it.kind.ordinal }
            .thenComparator { a, b ->
                val x = waitingSince(a)
                val y = waitingSince(b)
                when {
                    x == null && y == null -> 0
                    x == null -> 1
                    y == null -> -1
                    else -> x.compareTo(y)
                }
            }
    )
