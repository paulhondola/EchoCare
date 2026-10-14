package bia.sentinela.home

import bia.sentinela.R
import bia.sentinela.SeniorRow
import bia.sentinela.ui.Tone
import kotlinx.serialization.Serializable

// The destinations of the signed-in app (seniors §8.2), as type-safe routes.

/** The seniors the caller reaches as [role]: the medic's and the caregiver's home. */
@Serializable
data class SeniorsRoute(val role: String)

/** One senior's page. */
@Serializable
data class SeniorRoute(val id: String)

/** The senior's home: their own page. */
@Serializable
data object OwnRoute

/** The DAS home. Empty until incidents exist in the app (UC-11). */
@Serializable
data object IncidentsRoute

/** „Pacient nou”: the medic's form, empty, or filled from the senior [id] (seniors §9.1). */
@Serializable
data class EnrollRoute(val id: String? = null)

/** Where [role] lands after sign-in. [role] is one of auth.ROLES. */
fun homeFor(role: String): Any = when (role) {
    "medic", "caregiver" -> SeniorsRoute(role)
    "senior" -> OwnRoute
    else -> IncidentsRoute
}

/** A card opens the senior's page, except a medic's draft, which opens the form (seniors §9.1). */
fun openFor(role: String, senior: SeniorRow): Any = when {
    role == "medic" && senior.state == "draft" -> EnrollRoute(senior.id)
    else -> SeniorRoute(senior.id)
}

/** „Editează” shows while the medic may still edit: PUT refuses past `submitted` (04 §2). */
fun editable(state: String) = state == "draft" || state == "submitted"

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
    "unreachable" to R.string.state_unreachable
)

/** The colour of each state's chip, the same as on the dashboard (dashboard/src/utils/labels.ts). */
val STATE_TONES = mapOf(
    "draft" to Tone.Muted,
    "submitted" to Tone.Link,
    "accepted" to Tone.Link,
    "active" to Tone.Verde,
    "refused" to Tone.Galben,
    "wrong_number" to Tone.Galben,
    "unreachable" to Tone.Galben
)
