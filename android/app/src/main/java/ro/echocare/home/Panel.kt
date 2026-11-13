package ro.echocare.home

import androidx.annotation.StringRes
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import ro.echocare.R
import ro.echocare.SeniorPage
import ro.echocare.SeniorRow

// The medic's panel: the groups of her patients, the actions on one, and the enrollment stages
// (UC-12, 03 §7, UC-04). Plain Kotlin, tested on the JVM. Group and PatientAction are built here
// from the API's strings, never decoded: a state or code this build does not know must not crash.

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

internal fun instantOf(text: String?): Instant? =
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

// The medic home's strip (design 2026-11-13 medic home): the codes of active seniors, and those at DAS.
data class Counts(val red: Int, val yellow: Int, val green: Int, val atDas: Int)

fun countsOf(rows: List<SeniorRow>): Counts = Counts(
    red = rows.count { it.state == "active" && it.code == "red" },
    yellow = rows.count { it.state == "active" && it.code == "yellow" },
    green = rows.count { it.state == "active" && it.code == "green" },
    atDas = rows.count { it.state == "submitted" }
)

enum class PatientAction { CallAgain, Withdraw, Sign, Edit }

// The consent text and its signature belong before the welcome call: until acceptance, signed
// or not, so a saved signature shows „Semnat” in its place (G7, UC-01 step 5, UC-04).
fun showsConsent(page: SeniorPage): Boolean = page.state in setOf("draft", "submitted", "accepted")

// Not yet signed, and not past acceptance (UC-04).
fun signable(page: SeniorPage): Boolean = showsConsent(page) && page.signedAt == null

// The state in the medic's words on a card, for a state whose chip does not say it all
// (UC-12). `wrong_number` and `unreachable` have none: their chip says it.
fun says(state: String): Int? = when (state) {
    "accepted" -> R.string.says_welcome_pending
    else -> null
}

// The actions on the medic's own patient.
fun actionsFor(page: SeniorPage): List<PatientAction> = when (page.state) {
    "draft" -> emptyList()
    "wrong_number", "unreachable" -> listOf(PatientAction.CallAgain, PatientAction.Edit)
    "active" -> listOf(PatientAction.Withdraw, PatientAction.Edit)
    "submitted", "accepted" -> if (signable(
            page
        )
    ) {
        listOf(PatientAction.Sign, PatientAction.Edit)
    } else {
        listOf(PatientAction.Edit)
    }
    else -> listOf(PatientAction.Edit)
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

// The consent line's words (04 §1); a decision or method a later server adds shows raw.
val CONSENT_DECISIONS = mapOf(
    "given" to R.string.consent_given,
    "refused" to R.string.consent_refused,
    "withdrawn" to R.string.consent_withdrawn
)

val CONSENT_METHODS = mapOf(
    "call" to R.string.consent_call,
    "app" to R.string.consent_app,
    "medic" to R.string.consent_medic,
    "das" to R.string.consent_das
)

private val romanian = Locale.forLanguageTag("ro")
private val dayMonth = DateTimeFormatter.ofPattern("d MMM", romanian)
private val dayMonthYear = DateTimeFormatter.ofPattern("d MMM yyyy", romanian)

// A stage's date, "4 nov."; with [year], "4 nov. 2026". An unreadable date shows as sent.
fun shortDate(iso: String, zone: ZoneId, year: Boolean = false): String =
    instantOf(iso)?.atZone(zone)?.let { (if (year) dayMonthYear else dayMonth).format(it) } ?: iso
