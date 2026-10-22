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
import ro.echocare.R
import ro.echocare.TriggerEvent
import ro.echocare.enroll.Refusal
import ro.echocare.home.Failure
import ro.echocare.ui.Tone

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

/**
 * Newest first, the newest being the one shown open. GET /incidents/{id} sends the calls oldest
 * first (by creation, then attempt); their start time cannot order them, since an unanswered or
 * queued call never started.
 */
fun newestFirst(calls: List<IncidentCall>): List<IncidentCall> = calls.asReversed()

/**
 * Whether [callId] shows its transcript: as the dispatcher [toggled] it, else open only when it
 * is the newest, so a call that joins the incident while the page is open opens itself.
 */
fun expanded(callId: String, newestId: String, toggled: Map<String, Boolean>): Boolean =
    toggled[callId] ?: (callId == newestId)

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

/** The event's place as the page shows it; [accuracy] in whole metres, null when unknown. */
data class Location(val latitude: String, val longitude: String, val accuracy: Int?)

/** Null without coordinates. An unknown accuracy is left out, never shown as ±0 m. */
fun location(event: TriggerEvent): Location? {
    val lat = event.latitude ?: return null
    val lng = event.longitude ?: return null
    return Location(lat.toString(), lng.toString(), event.accuracy?.let { Math.round(it).toInt() })
}

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

/**
 * The colour of a status's chip and card bar, as the dashboard's: red open, yellow in progress,
 * green resolved. A status this build does not know is muted.
 */
fun statusTone(status: String): Tone = when (status) {
    "open" -> Tone.Rosu
    "in_progress" -> Tone.Galben
    "resolved" -> Tone.Verde
    else -> Tone.Muted
}

/** The one action the pinned bar offers (UC-11 steps 2 and 4). */
enum class Act { Take, Resolve }

/** Preiau while open, Rezolvat while in progress for any DAS employee, else nothing. */
fun actFor(status: String): Act? = when (status) {
    "open" -> Act.Take
    "in_progress" -> Act.Resolve
    else -> null
}

/** One line over the pinned bar after a refused Preiau or Trimite. */
sealed interface Notice {
    /** "Preluat deja de {name}." */
    data class TakenBy(val name: String) : Notice

    /** [text] is a string resource id. */
    data class Says(val text: Int) : Notice

    /** Signed out or no longer registered: sign-in replaces the screen. */
    data class Ends(val failure: Failure) : Notice
}

/** What a refused [act] tells the dispatcher, in the dashboard's words (commands.ts). */
fun noticeAfter(refusal: Refusal, act: Act): Notice = when (refusal) {
    is Refusal.AlreadyDone -> when {
        act == Act.Resolve -> Notice.Says(R.string.already_resolved)
        refusal.takenByName != null -> Notice.TakenBy(refusal.takenByName)
        else -> Notice.Says(R.string.incident_changed)
    }

    Refusal.WrongState -> Notice.Says(R.string.incident_changed)

    is Refusal.Failed -> when (refusal.failure) {
        Failure.NotAllowed -> Notice.Says(R.string.not_allowed_action)
        Failure.NotFound -> Notice.Says(R.string.incident_gone)
        Failure.SignedOut, Failure.NotRegistered -> Notice.Ends(refusal.failure)
        Failure.NoConnection -> Notice.Says(R.string.send_failed)
    }

    // The form checks what the server would refuse; anything else is a failed send
    is Refusal.Invalid, is Refusal.Incomplete, Refusal.PhoneTaken -> Notice.Says(
        R.string.send_failed
    )
}

/** The resolve note's limit (04 §2). */
const val NOTE_MAX = 1000

/** Trimite needs an outcome and a note of 1 to [NOTE_MAX] characters (04 §2). */
fun canSend(outcome: String?, note: String): Boolean =
    outcome != null && note.isNotBlank() && note.length <= NOTE_MAX

/** The five outcomes of 04 §2, in the dashboard's order and words. */
val OUTCOMES = listOf(
    "senior_ok" to R.string.outcome_senior_ok,
    "team_sent" to R.string.outcome_team_sent,
    "called_112" to R.string.outcome_called_112,
    "not_reached" to R.string.outcome_not_reached,
    "false_alarm" to R.string.outcome_false_alarm
)
