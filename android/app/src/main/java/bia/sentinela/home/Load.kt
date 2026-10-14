package bia.sentinela.home

import java.io.IOException
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import retrofit2.HttpException

/** What a refused or failed read means for the person (auth-layer §3.2, seniors §8.2). */
enum class Failure {
    NoConnection,
    NotFound,
    NotAllowed,
    SignedOut,
    NotRegistered;

    /** The app returns to sign-in: a grant revoked mid-session ends the session this way. */
    val endsSession get() = this == SignedOut || this == NotRegistered
}

/** [status] is the HTTP status, or null when no answer came at all. */
fun failureOf(status: Int?, reason: String?): Failure = when {
    // A 401 arrives only after the Authenticator's retry with a fresh token.
    status == 401 -> Failure.SignedOut
    status == 403 && reason == "not_registered" -> Failure.NotRegistered
    status == 403 -> Failure.NotAllowed
    status == 404 -> Failure.NotFound
    // No answer, a 5xx, or a status this build does not know: the last data stays up.
    else -> Failure.NoConnection
}

@Serializable
private data class Refusal(val detail: Detail? = null) {
    @Serializable
    data class Detail(val reason: String? = null)
}

private val lenient = Json { ignoreUnknownKeys = true }

/** The reason in a refusal body, `{"detail": {"reason": …}}` (04 §0); null for any other body. */
fun reasonOf(body: String?): String? = try {
    body?.let { lenient.decodeFromString<Refusal>(it).detail?.reason }
} catch (e: SerializationException) {
    // FastAPI's own 422 has a list under "detail"; a proxy's error page is not JSON at all.
    null
}

/** What a read answered. */
sealed interface Answer<out T> {
    data class Ok<T>(val value: T) : Answer<T>

    data class No(val failure: Failure) : Answer<Nothing>
}

/** Runs [call]. A refusal, a lost connection or an unreadable body becomes what it means. */
suspend fun <T> answer(call: suspend () -> T): Answer<T> = try {
    Answer.Ok(call())
} catch (e: HttpException) {
    Answer.No(failureOf(e.code(), reasonOf(e.response()?.errorBody()?.string())))
} catch (e: IOException) {
    Answer.No(failureOf(null, null))
} catch (e: SerializationException) {
    Answer.No(failureOf(null, null))
}

/** What a list or a page shows (seniors §8.2). */
sealed interface Load<out T> {
    data object Loading : Load<Nothing>

    /** [offline]: the last read failed, so [value] is the last data, under the banner (06 §1). */
    data class Ready<T>(val value: T, val offline: Boolean = false) : Load<T>

    data class Failed(val failure: Failure) : Load<Nothing>
}

/** The state after [answer]. With data on screen, losing the connection keeps the data. */
fun <T> Load<T>.after(answer: Answer<T>): Load<T> = when (answer) {
    is Answer.Ok -> Load.Ready(answer.value)

    is Answer.No -> if (answer.failure == Failure.NoConnection && this is Load.Ready) {
        copy(offline = true)
    } else {
        Load.Failed(answer.failure)
    }
}
