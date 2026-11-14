package ro.echocare.push

import java.io.IOException
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull

// What a push says, read the same way from a message and from the extras of a tapped
// notification (04 §6). Pure Kotlin, tested on the JVM.

/** The channel of every alert; the API names it in each alert (backend notify/service.py). */
const val ALERT_CHANNEL = "alerts"

/** The channel of "profile ready" notices; the API names it in each notice (backend notify/service.py). */
const val NOTICE_CHANNEL = "updates"

/** The data keys a push carries (04 §6); a tapped notification's extras carry the same. */
val PUSH_KEYS = listOf("type", "what", "senior_id", "incident_id")

/** A push as the app reads it: no name, code or reason, only ids (P18). */
sealed interface Push {
    /** Something about [seniorId] needs attention; [incidentId] only for DAS. */
    data class Alert(val seniorId: String, val incidentId: String?) : Push

    /** A medical profile of [seniorId] is ready for the medic to review (design §5.6). */
    data class Notice(val seniorId: String) : Push

    /** Something changed: an open screen re-reads (04 §6). */
    data object Refresh : Push
}

/**
 * [data] as a [Push]. A type this build does not know is a refresh, as is an alert missing its
 * senior (ADR-001 §2.3); null when [data] is no push at all, as a launcher tap's extras.
 */
fun pushFrom(data: Map<String, String?>): Push? {
    val type = data["type"] ?: return null
    val senior = data["senior_id"]
    return when {
        (type == "code_changed" || type == "incident") && senior != null ->
            Push.Alert(senior, data["incident_id"].takeIf { type == "incident" })

        type == "medical_record" && senior != null -> Push.Notice(senior)

        else -> Push.Refresh
    }
}

/** What a tapped notification opens: an alert, or a notice's senior as an alert with no incident. */
fun tappedFrom(data: Map<String, String?>): Push.Alert? = when (val push = pushFrom(data)) {
    is Push.Alert -> push
    is Push.Notice -> Push.Alert(push.seniorId, null)
    else -> null
}

/**
 * Runs [save] to its end on the calling thread: Firebase stops the service, and may end the process,
 * once `onNewToken` returns. Messages wait on that thread, tray alerts included, so [limit] keeps a
 * hung save from holding them back. A save that fails offline is left for the next app start.
 */
// ponytail: no retry while the app stays closed; WorkManager if tokens go stale in practice.
fun saveBeforeReturning(limit: Duration = 15.seconds, save: suspend () -> Unit) {
    runBlocking {
        withTimeoutOrNull(limit) {
            try {
                save()
            } catch (e: IOException) {
                // Saved again at the next sign-in or start (AuthViewModel.loadMe)
            }
        }
    }
}

/**
 * Refresh signals from pushes; a screen re-reads once a burst ends, while it is in front (04 §6).
 * One commit can send several, and each read asks for a whole page.
 */
object Refreshes {
    private val signals = MutableSharedFlow<Unit>(
        extraBufferCapacity = 1,
        onBufferOverflow = BufferOverflow.DROP_OLDEST
    )

    @OptIn(FlowPreview::class)
    val events: Flow<Unit> = signals.debounce(500.milliseconds)

    fun signal() {
        signals.tryEmit(Unit)
    }
}
