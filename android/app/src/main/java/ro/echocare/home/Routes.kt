package ro.echocare.home

import kotlinx.serialization.Serializable
import ro.echocare.R
import ro.echocare.SeniorRow
import ro.echocare.ui.Tone

// The destinations of the signed-in app (seniors §8.2), as type-safe routes.

/** The seniors the caller reaches as [role]: the medic's and the caregiver's home. */
@Serializable
data class SeniorsRoute(val role: String)

/** The medic's home: the Monitorizare and Înregistrare tiles (UC-12, UC-01). */
@Serializable
data object MedicHomeRoute

/** Monitorizare: the medic's patients by group (UC-12, 03 §7). */
@Serializable
data object MonitorRoute

/** Înregistrare: „Pacient nou” and the unfinished drafts (UC-01). */
@Serializable
data object RegisterRoute

/** One senior's page. */
@Serializable
data class SeniorRoute(val id: String)

/** The senior's home: their own page. */
@Serializable
data object OwnRoute

/** The DAS home: open and in-progress incidents (UC-12). */
@Serializable
data object IncidentsRoute

/** One incident's page (UC-11). */
@Serializable
data class IncidentRoute(val id: String)

/** „Rezolvare caz” for the incident [id] (UC-11 step 4). */
@Serializable
data class ResolveRoute(val id: String)

/** „Pacient nou”: the medic's form, empty, or filled from the senior [id] (seniors §9.1). */
@Serializable
data class EnrollRoute(val id: String? = null)

/** Where [role] lands after sign-in. [role] is one of auth.ROLES. */
fun homeFor(role: String): Any = when (role) {
    "medic" -> MedicHomeRoute
    "caregiver" -> SeniorsRoute(role)
    "senior" -> OwnRoute
    else -> IncidentsRoute
}

/** A card opens the senior's page, except a medic's draft, which opens the form (seniors §9.1). */
fun openFor(role: String, senior: SeniorRow): Any = when {
    role == "medic" && senior.state == "draft" -> EnrollRoute(senior.id)
    else -> SeniorRoute(senior.id)
}

/**
 * Where a tapped alert goes for the role the app is in (04 §6): DAS to the incident, otherwise to
 * the senior's page. The API reaches that page by every grant the person holds, whichever role the
 * app is in, so an alert about someone they care for opens in the DAS and senior roles too.
 */
fun alertRoute(seniorId: String, incidentId: String?, role: String): Any =
    incidentId?.takeIf { role == "das" }?.let(::IncidentRoute) ?: SeniorRoute(seniorId)

/**
 * The label of each enrollment state (05 §1). A state this build does not know has none and
 * shows no label: the server may add one later (ADR-001 §2.3).
 */
val STATE_LABELS = mapOf(
    "draft" to R.string.state_draft,
    "submitted" to R.string.state_submitted,
    "accepted" to R.string.state_accepted,
    "active" to R.string.state_active,
    "refused" to R.string.state_refused,
    "wrong_number" to R.string.state_wrong_number,
    "unreachable" to R.string.state_unreachable,
    "withdrawn" to R.string.state_withdrawn
)

/** The colour of each state's chip, the same as on the dashboard (dashboard/src/utils/labels.ts). */
val STATE_TONES = mapOf(
    "draft" to Tone.Muted,
    "submitted" to Tone.Link,
    "accepted" to Tone.Link,
    "active" to Tone.Verde,
    "refused" to Tone.Galben,
    "wrong_number" to Tone.Galben,
    "unreachable" to Tone.Galben,
    "withdrawn" to Tone.Muted
)

/**
 * The label of each code (03 §8). A code this build does not know has none and shows no chip
 * (ADR-001 §2.3).
 */
val CODE_LABELS = mapOf(
    "green" to R.string.code_green,
    "yellow" to R.string.code_yellow,
    "red" to R.string.code_red
)

/** The colour of each code's chip and of a card's bar. */
val CODE_TONES = mapOf(
    "green" to Tone.Verde,
    "yellow" to Tone.Galben,
    "red" to Tone.Rosu
)

/** What started each call (05 §1), as the dashboard names it. Unknown: shown as it is. */
/** A transcript answer's question (05 §2) under the medic's transcript. Unknown: shown raw. */
val ANSWER_FIELDS = mapOf(
    "feeling" to R.string.answer_feeling,
    "orientation" to R.string.answer_orientation,
    "shelter" to R.string.answer_shelter,
    "identity" to R.string.answer_identity,
    "consent" to R.string.consent_label
)

val TRIGGER_LABELS = mapOf(
    "campaign" to R.string.trigger_campaign,
    "watch" to R.string.trigger_watch,
    "manual" to R.string.trigger_manual,
    "welcome" to R.string.trigger_welcome
)

/** The event behind an incident (05 §1), as the dashboard names it. Unknown: shown as it is. */
val EVENT_LABELS = mapOf(
    "sos_button" to R.string.event_sos_button,
    "fall" to R.string.event_fall,
    "high_pulse_at_rest" to R.string.event_high_pulse_at_rest,
    "inactivity" to R.string.event_inactivity,
    "manual_request" to R.string.event_manual_request
)

/** A call's state (05 §1), for a call with no final code yet. Unknown: shown as it is. */
val CALL_STATE_LABELS = mapOf(
    "queued" to R.string.call_queued,
    "ringing" to R.string.call_ringing,
    "in_progress" to R.string.call_in_progress,
    "unanswered" to R.string.call_unanswered,
    "failed" to R.string.call_failed,
    "completed" to R.string.call_completed,
    "handed_over" to R.string.call_handed_over,
    "dropped" to R.string.call_dropped,
    "canceled" to R.string.call_canceled
)
