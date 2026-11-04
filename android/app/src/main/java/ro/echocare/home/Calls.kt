package ro.echocare.home

import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import ro.echocare.CallRow
import ro.echocare.SeniorPage
import ro.echocare.ui.Tone

// The short call history on one senior's page (UC-12): what each row shows, tested on the JVM.
// No transcript: a caregiver reaches the calls but not what was said (01 §6).

/** How many calls the page lists: a short history, not the medic's full one. */
const val RECENT_CALLS = 5

/** The newest calls, the canceled ones left out: they never rang (03 §9). */
fun recentCalls(calls: List<CallRow>): List<CallRow> =
    calls.filter { it.state != "canceled" }.take(RECENT_CALLS)

/** A call's result as its row shows it: the code it ended with, else the state it is in. */
sealed interface Outcome {
    data class Code(val code: String) : Outcome

    data class State(val state: String) : Outcome
}

/** A code this build does not know shows the state instead (ADR-001 §2.3). */
fun outcome(call: CallRow): Outcome =
    call.finalSeverity?.takeIf { it in CODE_TONES }?.let(Outcome::Code) ?: Outcome.State(call.state)

/** A call that rings or is live stands out; any other state is muted. */
fun stateTone(state: String): Tone =
    if (state == "ringing" || state == "in_progress") Tone.Galben else Tone.Muted

private val callTimeFormat = DateTimeFormatter.ofPattern("dd.MM HH:mm")

/** When the call ended, else when it was picked up, else when it is due; in [zone]. */
fun callTime(call: CallRow, zone: ZoneId): String = callTimeFormat.format(
    Instant.parse(call.endedAt ?: call.startedAt ?: call.dueAt).atZone(zone)
)

/** The "call in progress" badge (UC-12); an older API that does not say shows none. */
fun showsCallBadge(senior: SeniorPage): Boolean = senior.callInProgress == true
