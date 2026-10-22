package ro.echocare.das

import java.time.Duration
import java.time.Instant
import ro.echocare.IncidentRow

// What the DAS screens show, worked out from the API's answers (UC-11, UC-12). Pure, tested on
// the JVM.

/** The statuses the DAS app asks for: resolved incidents are the dashboard's (04 §1). */
const val ACTIVE = "open,in_progress"

/** The home's two sections, each with the longest wait first (design §"The list"). */
data class Sections(val open: List<IncidentRow>, val inProgress: List<IncidentRow>)

/**
 * Open by opening time, in progress by take time or else opening time, both oldest first, as
 * the dashboard's columns(). A status this build does not know is left out (ADR-001 §2.3).
 */
fun sections(rows: List<IncidentRow>): Sections = Sections(
    open = rows.filter { it.status == "open" }.sortedBy { Instant.parse(it.openedAt) },
    inProgress = rows.filter { it.status == "in_progress" }
        .sortedBy { Instant.parse(it.takenAt ?: it.openedAt) }
)

/** How long ago something happened, as the dashboard's since(): "acum 4 min", "acum 2 h 5 min". */
sealed interface Ago {
    data object Moments : Ago

    data class Minutes(val m: Long) : Ago

    data class Hours(val h: Long, val m: Long) : Ago

    /** A day or more: shown as the date. */
    data class On(val at: Instant) : Ago
}

/** [iso] is FastAPI's UTC time, with or without fractions and an offset. */
fun ago(iso: String, now: Instant): Ago {
    val at = Instant.parse(iso)
    val minutes = Duration.between(at, now).toMinutes()
    return when {
        // Under a minute, or a phone clock behind the server's
        minutes < 1 -> Ago.Moments
        minutes < 60 -> Ago.Minutes(minutes)
        minutes < 24 * 60 -> Ago.Hours(minutes / 60, minutes % 60)
        else -> Ago.On(at)
    }
}
