package ro.echocare.wear.monitoring

// „Help is coming” (design 2026-11-14, watch senior UI, as `Monitor.swift`): „Încercăm din nou…”
// after this long without the phone's ack, and the ✓ screen goes home after this long
const val HELP_RETRYING_MS = 20_000L
const val HELP_SHOWN_MS = 60_000L

enum class HelpPhase { SENDING, RETRYING, RECEIVED }

/**
 * The last event the senior sent, by „Nu mă simt bine”, „Nu” or silence, and when the phone acked
 * it: the phone acks only once FastAPI has recorded it (04 §3), so ✓ means the team has it.
 */
data class Alert(val id: String, val sentAtMs: Long, val receivedAtMs: Long? = null) {
    fun phase(nowMs: Long): HelpPhase = when {
        receivedAtMs != null -> HelpPhase.RECEIVED
        nowMs - sentAtMs >= HELP_RETRYING_MS -> HelpPhase.RETRYING
        else -> HelpPhase.SENDING
    }

    /**
     * Not while sending: a second, panicked tap on the help button lands on this screen. Once
     * retrying, the senior can leave, as the event stays queued; once received, they can too.
     */
    fun canDismiss(nowMs: Long): Boolean = phase(nowMs) != HelpPhase.SENDING

    /** The phone's ack. Only this alert's id counts: an older, resent event's ack changes nothing. */
    fun acked(ackId: String, nowMs: Long): Alert =
        if (ackId == id && receivedAtMs == null) copy(receivedAtMs = nowMs) else this
}
