package ro.echocare.home

import java.io.IOException
import kotlinx.serialization.SerializationException
import retrofit2.HttpException
import ro.echocare.SeniorPage
import ro.echocare.enroll.Refusal
import ro.echocare.enroll.refusalOf

// The medic's commands on her patient, „Sună din nou” and the withdrawal (UC-04, UC-12, 04 §2),
// and what each answer means for the page. Pure, tested on the JVM.

/**
 * What a command answered. Named apart from [Outcome], a call row's result. The page rereads
 * after [Done] and [Refused]; [Offline] keeps the page as it is.
 */
sealed interface CommandOutcome {
    data object Done : CommandOutcome

    /** The server said no; [reason] is a 409's reason, null for a 403, 404 or 422. */
    data class Refused(val reason: String?) : CommandOutcome

    /** No answer, or a 5xx: nothing is known to have changed (seniors §8.2). */
    data object Offline : CommandOutcome
}

/** The outcome of HTTP [status] with [body]; a null status is no answer at all. */
fun commandOutcome(status: Int?, body: String?): CommandOutcome {
    if (status != null && status in 200..299) return CommandOutcome.Done
    return when (val refusal = refusalOf(status, body)) {
        // refusalOf reads wrong_state and a 409 reason this build does not know alike
        Refusal.WrongState -> CommandOutcome.Refused("wrong_state")
        is Refusal.AlreadyDone -> CommandOutcome.Refused("already_done")
        Refusal.PhoneTaken -> CommandOutcome.Refused("phone_taken")
        is Refusal.Failed -> if (refusal.failure == Failure.NoConnection) {
            CommandOutcome.Offline
        } else {
            CommandOutcome.Refused(null)
        }
        is Refusal.Invalid, is Refusal.Incomplete -> CommandOutcome.Refused(null)
    }
}

/** Runs [call]: a refusal's status and body, or a lost connection, become their outcome. */
suspend fun command(call: suspend () -> Unit): CommandOutcome = try {
    call()
    CommandOutcome.Done
} catch (e: HttpException) {
    commandOutcome(e.code(), e.response()?.errorBody()?.string())
} catch (e: IOException) {
    commandOutcome(null, null)
} catch (e: SerializationException) {
    // The command went through; only its answer did not read. The reread shows where it stands.
    CommandOutcome.Done
}

/**
 * A number saved in the form for a senior the calls could not reach: no call is queued for it
 * (04 §2), so the page says to press „Sună din nou”. [before] is the number the page showed
 * when „Editează datele” was pressed.
 */
fun numberChanged(before: String, now: SeniorPage): Boolean =
    now.phone != before && now.state in TO_RESOLVE

private val TO_RESOLVE = setOf("wrong_number", "unreachable")
