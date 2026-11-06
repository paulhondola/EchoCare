package ro.echocare.home

import ro.echocare.SeniorPage
import ro.echocare.enroll.Refusal
import ro.echocare.enroll.Sent
import ro.echocare.enroll.refusalOf
import ro.echocare.enroll.send

// The medic's commands on her patient, „Sună din nou” and the withdrawal (UC-04, UC-12, 04 §2),
// and what each answer means for the page. Pure, tested on the JVM.

/**
 * What a command answered. Named apart from [Outcome], a call row's result. The page rereads
 * after [Done] and [Refused]; [Offline] keeps the page as it is.
 */
sealed interface CommandOutcome {
    data object Done : CommandOutcome

    /**
     * The server said no; [reason] is a 409's reason, "not_found" for a 404, "invalid" for a 422,
     * null for a 403 or anything else.
     */
    data class Refused(val reason: String?) : CommandOutcome

    /** No answer, or a 5xx: nothing is known to have changed (seniors §8.2). */
    data object Offline : CommandOutcome
}

/** The outcome of HTTP [status] with [body]; a null status is no answer at all. */
fun commandOutcome(status: Int?, body: String?): CommandOutcome = if (status != null &&
    status in 200..299
) {
    CommandOutcome.Done
} else {
    outcomeOf(refusalOf(status, body))
}

/** What [refusal] means for the page, as [send] reads it for the form (seniors §9.3). */
private fun outcomeOf(refusal: Refusal): CommandOutcome = when (refusal) {
    // refusalOf reads wrong_state and a 409 reason this build does not know alike
    Refusal.WrongState -> CommandOutcome.Refused("wrong_state")
    is Refusal.AlreadyDone -> CommandOutcome.Refused("already_done")
    Refusal.PhoneTaken -> CommandOutcome.Refused("phone_taken")
    is Refusal.Failed -> when (refusal.failure) {
        Failure.NoConnection -> CommandOutcome.Offline
        Failure.NotFound -> CommandOutcome.Refused("not_found")
        else -> CommandOutcome.Refused(null)
    }
    is Refusal.Invalid, is Refusal.Incomplete -> CommandOutcome.Refused("invalid")
}

/**
 * Runs [call] through the form's [send], so both read an answer alike: an unreadable body is
 * no connection, and the timed reread shows where the senior stands.
 */
suspend fun command(call: suspend () -> Unit): CommandOutcome = when (val sent = send(call)) {
    is Sent.Ok -> CommandOutcome.Done
    is Sent.No -> outcomeOf(sent.refusal)
}

/**
 * The notice once a reread went through: the connection is back, so „Fără conexiune” goes. A
 * refusal stays until the next command.
 */
fun noticeAfterRead(notice: CommandOutcome?): CommandOutcome? =
    notice.takeIf { it != CommandOutcome.Offline }

/**
 * A number saved in the form for a senior the calls could not reach: no call is queued for it
 * (04 §2), so the page says to press „Sună din nou”. [before] is the number the page showed
 * when „Editează datele” was pressed.
 */
fun isNewNumberToCall(before: String, now: SeniorPage): Boolean =
    now.phone != before && now.state in TO_RESOLVE

private val TO_RESOLVE = setOf("wrong_number", "unreachable")
