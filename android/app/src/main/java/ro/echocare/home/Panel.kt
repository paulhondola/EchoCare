package ro.echocare.home

import androidx.annotation.StringRes
import java.time.Instant
import ro.echocare.R
import ro.echocare.SeniorPage
import ro.echocare.SeniorRow

// The medic's panel: the groups of her patients, the actions on one, and the enrollment stages
// (UC-12, 03 §7, UC-04). Plain Kotlin, tested on the JVM. Group and Action are built here from
// the API's strings, never decoded: a state or code this build does not know must not crash.

enum class Group(@StringRes val title: Int) {
    Urgent(R.string.group_urgent),
    ToResolve(R.string.group_to_resolve),
    InProgress(R.string.group_in_progress),
    Green(R.string.group_green),
    AtDas(R.string.group_at_das),
    Inactive(R.string.group_inactive)
}

// null for a draft: it is not a patient of the panel yet, only counted.
fun groupOf(row: SeniorRow): Group? = when (row.state) {
    "draft" -> null
    "active" -> if (row.code == "red" || row.code == "yellow") Group.Urgent else Group.Green
    "wrong_number", "unreachable" -> Group.ToResolve
    "accepted" -> Group.InProgress
    "submitted" -> Group.AtDas
    else -> Group.Inactive
}

private fun instantOf(text: String?): Instant? =
    text?.let { runCatching { Instant.parse(it) }.getOrNull() }

// Red before yellow, then the longest-waiting first; no `since` last.
private val urgentOrder: Comparator<SeniorRow> =
    compareBy<SeniorRow> { if (it.code == "red") 0 else 1 }
        .thenComparator { a, b ->
            val x = instantOf(a.since)
            val y = instantOf(b.since)
            when {
                x == null && y == null -> 0
                x == null -> 1
                y == null -> -1
                else -> x.compareTo(y)
            }
        }

// Groups in the enum's order, empty ones dropped; the API's order inside all but Urgent.
fun panel(rows: List<SeniorRow>): List<Pair<Group, List<SeniorRow>>> {
    val byGroup = rows.mapNotNull { row ->
        groupOf(row)?.let { it to row }
    }.groupBy({ it.first }, { it.second })
    return Group.entries.mapNotNull { group ->
        val members = byGroup[group] ?: return@mapNotNull null
        group to if (group == Group.Urgent) members.sortedWith(urgentOrder) else members
    }
}

data class Counts(val red: Int, val yellow: Int, val toResolve: Int, val drafts: Int)

fun countsOf(rows: List<SeniorRow>): Counts = Counts(
    red = rows.count { it.state == "active" && it.code == "red" },
    yellow = rows.count { it.state == "active" && it.code == "yellow" },
    toResolve = rows.count { groupOf(it) == Group.ToResolve },
    drafts = rows.count { it.state == "draft" }
)

enum class Action { CallAgain, Withdraw, Sign, Edit }

// Not yet signed, and not past acceptance (UC-04).
fun signable(page: SeniorPage): Boolean =
    page.state in setOf("draft", "submitted", "accepted") && page.signedAt == null

// The actions on the medic's own patient.
fun actionsFor(page: SeniorPage): List<Action> = when (page.state) {
    "draft" -> emptyList()
    "wrong_number", "unreachable" -> listOf(Action.CallAgain, Action.Edit)
    "active" -> listOf(Action.Withdraw, Action.Edit)
    "submitted", "accepted" -> if (signable(
            page
        )
    ) {
        listOf(Action.Sign, Action.Edit)
    } else {
        listOf(Action.Edit)
    }
    else -> listOf(Action.Edit)
}

data class Stage(@StringRes val label: Int, val at: String?, val reached: Boolean)

// The enrollment's four stages and, for an end state, a fifth (03 §7). `at` is null when the API
// sent no date (an older API).
fun stagesOf(page: SeniorPage): List<Stage> {
    val reachedCount = when (page.state) {
        "submitted" -> 2
        "accepted", "wrong_number", "unreachable", "refused" -> 3
        "active", "withdrawn" -> 4
        else -> 1 // draft, or a state this build does not know
    }
    val stages = listOf(
        Stage(R.string.stage_draft, page.createdAt, reachedCount >= 1),
        Stage(R.string.stage_submitted, page.submittedAt, reachedCount >= 2),
        Stage(R.string.stage_accepted, page.acceptedAt, reachedCount >= 3),
        Stage(R.string.stage_active, page.consentGivenAt, reachedCount >= 4)
    )
    val end = when (page.state) {
        "refused" -> Stage(R.string.stage_refused, page.consent?.at, true)
        "withdrawn" -> Stage(R.string.stage_withdrawn, page.consent?.at, true)
        "wrong_number" -> Stage(R.string.stage_wrong_number, null, true)
        "unreachable" -> Stage(R.string.stage_unreachable, null, true)
        else -> null
    }
    return if (end == null) stages else stages + end
}
