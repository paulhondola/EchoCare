package ro.echocare.push

import java.io.IOException
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull

// What a push says, read the same way from a message and from the extras of a tapped
// notification (04 §6). Pure Kotlin, tested on the JVM.

/** The channel of every alert; the API names it in each alert (backend notify/service.py). */
const val ALERT_CHANNEL = "alerts"

/** The data keys a push carries (04 §6); a tapped notification's extras carry the same. */
val PUSH_KEYS = listOf("type", "what", "senior_id", "incident_id")

/** A push as the app reads it: no name, code or reason, only ids (P18). */
sealed interface Push {
    /** Something about [seniorId] needs attention; [incidentId] only for DAS. */
    data class Alert(val seniorId: String, val incidentId: String?) : Push

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

        else -> Push.Refresh
    }
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

/** Refresh signals from pushes; a screen re-reads on each while it is in front (04 §6). */
object Refreshes {
    private val signals = MutableSharedFlow<Unit>(
        extraBufferCapacity = 1,
        onBufferOverflow = BufferOverflow.DROP_OLDEST
    )
    val events: SharedFlow<Unit> = signals

    fun signal() {
        signals.tryEmit(Unit)
    }
}
