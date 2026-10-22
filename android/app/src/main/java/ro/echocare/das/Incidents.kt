package ro.echocare.das

import java.net.URLEncoder
import java.time.Duration
import java.time.Instant
import kotlin.text.Charsets.UTF_8
import ro.echocare.CallReport
import ro.echocare.CallTurn
import ro.echocare.IncidentCall
import ro.echocare.IncidentRow
import ro.echocare.IncidentSenior
import ro.echocare.TriggerEvent

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

/** What the senior said: the quote of the latest red report that has one, across the calls. */
fun seniorsWords(calls: List<IncidentCall>): String? = calls
    .flatMap { it.reports }
    .filter { it.severity == "red" && !it.quote.isNullOrBlank() }
    .maxByOrNull { Instant.parse(it.at) }
    ?.quote

/** A call not started yet, then by start time, newest first: the newest is the one shown open. */
fun newestFirst(calls: List<IncidentCall>): List<IncidentCall> = calls.sortedWith(
    compareBy<IncidentCall> { it.startedAt != null }
        .thenByDescending { it.startedAt?.let(Instant::parse) }
)

/** The "Apel în curs" badge (UC-12): a call ringing or live. */
fun callLive(calls: List<IncidentCall>): Boolean =
    calls.any { it.state == "ringing" || it.state == "in_progress" }

/** One line of a call as the page shows it: what was said, or a code reported at that moment. */
sealed interface Line {
    val at: String

    data class Said(val turn: CallTurn) : Line {
        override val at get() = turn.at
    }

    data class Flagged(val report: CallReport) : Line {
        override val at get() = report.at
    }
}

/** Turns and reports in time order; a report at the same moment as a turn follows it. */
fun timeline(call: IncidentCall): List<Line> =
    (call.turns.map(Line::Said) + call.reports.map(Line::Flagged))
        .sortedBy { Instant.parse(it.at) }

/** Seniors have no city field; the service is DAS Timișoara (design §"Phone and Maps"). */
const val CITY = "Timișoara"

/**
 * "Deschide în Hărți": the event's location when it has one, else the street address. Null when
 * there is neither, so the button is not shown.
 */
fun mapsUri(senior: IncidentSenior, event: TriggerEvent?): String? {
    val lat = event?.latitude
    val lng = event?.longitude
    if (lat != null && lng != null) return "geo:$lat,$lng?q=$lat,$lng"
    val street = senior.street?.takeIf { it.isNotBlank() } ?: return null
    val place = listOfNotNull(street, senior.streetNumber).joinToString(" ") + ", $CITY"
    return "geo:0,0?q=" + URLEncoder.encode(place, UTF_8).replace("+", "%20")
}
