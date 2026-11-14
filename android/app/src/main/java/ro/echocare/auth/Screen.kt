package ro.echocare.auth

import ro.echocare.Me
import ro.echocare.R

/** The roles this build has screens for, in GET /me's order (auth-layer §3.3). */
val ROLES = listOf("das", "medic", "caregiver", "senior")

/** Each role's name, for the role picker and the profile page. */
val ROLE_LABELS = mapOf(
    "das" to R.string.role_das,
    "medic" to R.string.role_medic,
    "caregiver" to R.string.role_caregiver,
    "senior" to R.string.role_senior
)

/** What the sign-in flow shows (auth-layer §8.2). [error] is a string resource id. */
sealed interface Screen {
    /** Signed out: what EchoCare does, with *Intrați* leading on to [Phone]. */
    data object Landing : Screen

    data class Phone(val error: Int? = null) : Screen

    data class Code(val error: Int? = null) : Screen

    data object Loading : Screen

    data object NotRegistered : Screen

    data object Unavailable : Screen

    data class PickRole(val roles: List<String>) : Screen

    /** The app in [role]; [roles] are every role it may switch to, from the profile page. */
    data class Home(val role: String, val displayName: String, val roles: List<String>) : Screen {
        val canSwitch: Boolean get() = roles.size > 1
    }
}

/** The granted roles this build knows, once each, in [ROLES] order. */
fun rolesOf(me: Me): List<String> = me.grants.map { it.role }.let { granted ->
    ROLES.filter {
        it in
            granted
    }
}

/**
 * The screen after GET /me answers 200 (auth-layer §8.2). [saved] is the role picked earlier.
 * Roles this build does not know are dropped (app/AGENTS.md: decode leniently); AL3 counts distinct roles.
 */
fun screenFor(me: Me, saved: String?): Screen {
    val roles = rolesOf(me)
    return when {
        roles.isEmpty() -> Screen.NotRegistered
        roles.size == 1 -> Screen.Home(roles.single(), me.displayName, roles)
        saved != null && saved in roles -> Screen.Home(saved, me.displayName, roles)
        else -> Screen.PickRole(roles)
    }
}

/**
 * The screen after GET /me fails with HTTP [status] (auth-layer §3.2). A 401 arrives only after the
 * Authenticator's retry, so it means sign in again. /me refuses with 403 only for `not_registered`.
 */
fun screenFor(status: Int): Screen = when (status) {
    401 -> Screen.Phone()
    403 -> Screen.NotRegistered
    else -> Screen.Unavailable
}

/** What the person typed, as E.164 (auth-layer §7.1). The server normalizes again. */
fun toE164(raw: String): String {
    val digits = raw.replace(Regex("[\\s\\-.()]"), "")
    return when {
        digits.startsWith("00") -> "+" + digits.drop(2)
        digits.startsWith("0") -> "+40" + digits.drop(1)
        digits.startsWith("7") -> "+40$digits"
        else -> digits
    }
}
