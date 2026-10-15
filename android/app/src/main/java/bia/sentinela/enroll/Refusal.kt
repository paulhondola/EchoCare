package bia.sentinela.enroll

import bia.sentinela.R
import bia.sentinela.home.Failure
import bia.sentinela.home.failureOf
import java.io.IOException
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import retrofit2.HttpException
import retrofit2.Response

// What a refused command means for the form (seniors §9.3). Pure, tested on the JVM.

/** A refused command, read from either body: FastAPI's own 422 or ours (04 §0). */
sealed interface Refusal {
    /** FastAPI's 422, `{"detail": [{"loc": ["body", …]}]}`: the body fields it names. */
    data class Invalid(val fields: List<String>) : Refusal

    /** 422 `incomplete`: what DAS still needs, named in `missing` (04 §2). */
    data class Incomplete(val missing: List<String>) : Refusal

    data object AlreadyDone : Refusal

    /** The senior moved on meanwhile. */
    data object WrongState : Refusal

    /** Anything else means what it means for a read (seniors §8.2). */
    data class Failed(val failure: Failure) : Refusal
}

/** The refusal in HTTP [status] and its [body]. A null status is no answer at all. */
fun refusalOf(status: Int?, body: String?): Refusal {
    val detail = detailOf(body)
    val ours = detail as? JsonObject
    val reason = ours?.get("reason").text()
    return when {
        status == 422 && detail is JsonArray -> Refusal.Invalid(
            detail.mapNotNull(::fieldOf).distinct()
        )

        status == 422 && reason == "incomplete" -> Refusal.Incomplete(
            (ours?.get("missing") as? JsonArray)?.mapNotNull { it.text() }.orEmpty()
        )

        status == 422 -> Refusal.Invalid(emptyList())

        status == 409 && reason == "already_done" -> Refusal.AlreadyDone

        // wrong_state, or a reason a later server adds: the senior is read again
        status == 409 -> Refusal.WrongState

        else -> Refusal.Failed(failureOf(status, reason))
    }
}

private fun detailOf(body: String?): JsonElement? = try {
    (body?.let { Json.parseToJsonElement(it) } as? JsonObject)?.get("detail")
} catch (e: SerializationException) {
    // A proxy's error page is not JSON at all
    null
}

/** `loc` is ["body", "phone"] for a field of the body; a path or the whole body names none. */
private fun fieldOf(error: JsonElement): String? {
    val loc = (error as? JsonObject)?.get("loc") as? JsonArray ?: return null
    return if (loc.size >= 2 && loc[0].text() == "body") loc[1].text() else null
}

private fun JsonElement?.text(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.content

/** What a command answered. */
sealed interface Sent<out T> {
    data class Ok<T>(val value: T) : Sent<T>

    data class No(val refusal: Refusal) : Sent<Nothing>
}

/** Runs [call]. A refusal, a lost connection or an unreadable body becomes what it means. */
suspend fun <T> send(call: suspend () -> T): Sent<T> = try {
    Sent.Ok(call())
} catch (e: HttpException) {
    Sent.No(refusalOf(e.code(), e.response()?.errorBody()?.string()))
} catch (e: IOException) {
    Sent.No(Refusal.Failed(Failure.NoConnection))
} catch (e: SerializationException) {
    Sent.No(Refusal.Failed(Failure.NoConnection))
}

/** A call that returns its [Response], such as a 204, refuses the way the others do. */
fun ensure(response: Response<*>) {
    if (!response.isSuccessful) throw HttpException(response)
}

/** The form's commands. */
enum class Action { Save, Add, Remove, Submit }

/** One line over the form's buttons. */
sealed interface Notice {
    /** [text] is a string resource id. */
    data class Says(val text: Int) : Notice

    /** „Lipsesc: …”, by the labels in [MISSING_LABELS]. */
    data class Missing(val names: List<String>) : Notice
}

/** What the form does after a refused command (seniors §9.3). */
sealed interface Then {
    /** A text under each field the server named. */
    data class Mark(val errors: Map<Field, Int>) : Then

    data class Show(val notice: Notice) : Then

    /** Read the senior again; step 4 shows the state they are in. */
    data object Reread : Then

    /** The form cannot go on, as in slice 3's table (seniors §8.2). */
    data class Stop(val failure: Failure) : Then
}

fun thenAfter(action: Action, refusal: Refusal): Then = when (refusal) {
    is Refusal.Invalid -> marks(action, refusal.fields)

    // Past draft the last caregiver stays (04 §2)
    is Refusal.Incomplete -> if (action == Action.Remove) {
        Then.Show(Notice.Says(R.string.last_caregiver))
    } else {
        Then.Show(Notice.Missing(refusal.missing))
    }

    // A repeated submit: already submitted, so step 4 shows that
    Refusal.AlreadyDone -> if (action == Action.Add) {
        Then.Show(Notice.Says(R.string.already_caregiver))
    } else {
        Then.Reread
    }

    Refusal.WrongState -> Then.Reread

    // The form keeps what was typed
    is Refusal.Failed -> if (refusal.failure == Failure.NoConnection) {
        Then.Show(Notice.Says(R.string.no_connection))
    } else {
        Then.Stop(refusal.failure)
    }
}

/** The fields of the body [action] sent that FastAPI named by [keys]. */
private fun marks(action: Action, keys: List<String>): Then {
    val sent = when (action) {
        Action.Save -> REGISTRATION
        Action.Add -> Step.Caregivers.fields
        Action.Remove, Action.Submit -> emptyList()
    }
    val errors = keys.mapNotNull { key -> sent.find { it.key == key } }.associateWith {
        when (it) {
            Field.Phone -> R.string.invalid_phone
            Field.CaregiverPhone -> R.string.caregiver_phone_invalid
            else -> R.string.field_invalid
        }
    }
    return if (errors.isEmpty()) {
        Then.Show(
            Notice.Says(R.string.field_invalid)
        )
    } else {
        Then.Mark(errors)
    }
}
