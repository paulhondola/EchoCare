package ro.echocare

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

// GET /me (auth-layer §3.3). Only the fields the app reads; roles stay strings (ADR-001 §2.3).
// [warningActive]: a weather warning is in force, shown on the senior's home (Q5).
@Serializable
data class Me(
    @SerialName("display_name") val displayName: String,
    val grants: List<Grant>,
    @SerialName("warning_active") val warningActive: Boolean = false
)

@Serializable
data class Grant(val role: String)

// One row of GET /seniors (seniors §3.3). The state stays a string: a later server may add one.
// [code], [reason] and [since] are the latest result of an active senior, else null (03 §8).
@Serializable
data class SeniorRow(
    val id: String,
    @SerialName("full_name") val fullName: String,
    @SerialName("form_of_address") val formOfAddress: String,
    @SerialName("phone_e164") val phone: String,
    @SerialName("phone_is_landline") val landline: Boolean,
    @SerialName("enrollment_state") val state: String,
    val code: String? = null,
    val reason: String? = null,
    val since: String? = null,
    // When the registration was made, sent to DAS and accepted (04 §1); null while it has not
    // happened, or from an older API. [watchState] is ok, not_worn or offline, a string for a
    // later server's value (UC-12, ADR-001 §2.3).
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("submitted_at") val submittedAt: String? = null,
    @SerialName("accepted_at") val acceptedAt: String? = null,
    @SerialName("watch_state") val watchState: String? = null
)

// GET /seniors/{id} (seniors §3.3): the row, the address with its access details (G13), the
// medic and the caregivers. The same for every role (seniors SE7).
@Serializable
data class SeniorPage(
    val id: String,
    @SerialName("full_name") val fullName: String,
    @SerialName("form_of_address") val formOfAddress: String,
    @SerialName("phone_e164") val phone: String,
    @SerialName("phone_is_landline") val landline: Boolean,
    @SerialName("enrollment_state") val state: String,
    val code: String? = null,
    val reason: String? = null,
    val since: String? = null,
    val street: String? = null,
    @SerialName("street_number") val streetNumber: String? = null,
    val block: String? = null,
    val staircase: String? = null,
    val floor: String? = null,
    val apartment: String? = null,
    @SerialName("intercom_code") val intercomCode: String? = null,
    @SerialName("key_holder") val keyHolder: String? = null,
    val landmark: String? = null,
    @SerialName("call_window") val callWindow: String? = null,
    val medic: Medic,
    val caregivers: List<Caregiver> = emptyList(),
    // One of her calls is ringing or live: the "call in progress" badge (UC-12). Null from an
    // older API, which reads as no.
    @SerialName("call_in_progress") val callInProgress: Boolean? = null,
    // The watch's state, for her caregivers and her medic (UC-12); null for anyone else, or from an
    // older API. A string: the server may add a state (ADR-001 §2.3)
    @SerialName("watch_state") val watchState: String? = null,
    // The timeline of the registration and of her consent (04 §1, G7); all null from an older API.
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("submitted_at") val submittedAt: String? = null,
    @SerialName("accepted_at") val acceptedAt: String? = null,
    val consent: ConsentState? = null,
    @SerialName("consent_given_at") val consentGivenAt: String? = null,
    @SerialName("signed_at") val signedAt: String? = null
)

// Her latest consent decision (04 §1). Decision and method stay strings: a later server may add
// one (ADR-001 §2.3). [at] is ISO-8601.
@Serializable
data class ConsentState(val decision: String, val method: String, val at: String)

// POST /seniors/{id}/signature's body (04 §2): the consent text's version and the strokes of the
// signature, each a list of [x, y] points.
@Serializable
data class SignatureForm(
    @SerialName("text_version") val textVersion: String,
    val strokes: List<List<List<Float>>>
)

// One row of GET /seniors/{id}/calls (04 §1), newest first. What a caregiver may see: no turns,
// no transcript (01 §6). [trigger] and [state] stay strings (ADR-001 §2.3).
@Serializable
data class CallRow(
    val id: String,
    val trigger: String,
    val state: String,
    @SerialName("due_at") val dueAt: String,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("ended_at") val endedAt: String? = null,
    @SerialName("final_severity") val finalSeverity: String? = null,
    val reason: String? = null
)

@Serializable
data class Medic(@SerialName("display_name") val displayName: String, val practice: String? = null)

@Serializable
data class Caregiver(
    @SerialName("user_id") val userId: String,
    @SerialName("display_name") val displayName: String,
    val relation: String? = null,
    @SerialName("phone_e164") val phone: String
)

// POST /seniors and PUT /seniors/{id}'s body: the whole registration (seniors §3.5). No defaults,
// so every field is sent, an empty one as null: PUT replaces every field.
@Serializable
data class SeniorForm(
    @SerialName("full_name") val fullName: String,
    @SerialName("form_of_address") val formOfAddress: String,
    val phone: String,
    @SerialName("call_window") val callWindow: String?,
    val street: String?,
    @SerialName("street_number") val streetNumber: String?,
    val block: String?,
    val staircase: String?,
    val floor: String?,
    val apartment: String?,
    @SerialName("intercom_code") val intercomCode: String?,
    @SerialName("key_holder") val keyHolder: String?,
    val landmark: String?
)

// POST /seniors/{id}/caregivers's body (seniors §3.5). The phone must be a mobile: caregivers
// sign in by SMS.
@Serializable
data class CaregiverForm(
    @SerialName("display_name") val displayName: String,
    val relation: String,
    val phone: String
)

// GET /profile/mock-call (design §4.2): the senior's due call, which the card answers in place of a
// phone. [trigger] stays a string (ADR-001 §2.3). [kind] and [level] are a campaign's, [consentText]
// a welcome call's, shown as the server sent it.
@Serializable
data class MockCall(
    @SerialName("call_id") val callId: String,
    val trigger: String,
    @SerialName("campaign_kind") val kind: String? = null,
    @SerialName("campaign_level") val level: String? = null,
    @SerialName("consent_text") val consentText: String? = null
)

// POST /calls/{id}/mock-answer's body (design §4.2), one shape per trigger. The defaults are not
// sent: a campaign answer is the three choices or [declined], a welcome answer is [consent].
@Serializable
data class MockAnswer(
    val feeling: String? = null,
    val day: String? = null,
    val shelter: String? = null,
    val declined: Boolean = false,
    val consent: Boolean? = null
)

// POST /me/events' body (04 §3). [type] is "manual_request" so far; [measuredAt] is ISO-8601 with
// an offset, and [id] is the phone's, so a resend is a duplicate.
@Serializable
data class EventForm(
    val id: String,
    val type: String,
    @SerialName("measured_at") val measuredAt: String
)

// POST /me/events' answer: [queued] when this event queued a call, [callId] the call it started or
// joined, null when no call was queued (a stale event, or a senior who is not active).
@Serializable
data class EventResult(
    val queued: Boolean = false,
    @SerialName("call_id") val callId: String? = null
)

// One row of GET /incidents (04 §1). [status] stays a string: a later server may add one.
@Serializable
data class IncidentRow(
    val id: String,
    @SerialName("senior_full_name") val seniorName: String,
    @SerialName("senior_form_of_address") val formOfAddress: String,
    val status: String,
    val reason: String,
    @SerialName("opened_at") val openedAt: String,
    @SerialName("taken_by_name") val takenByName: String? = null,
    @SerialName("taken_at") val takenAt: String? = null,
    @SerialName("handover_answered") val handoverAnswered: Boolean = false
)

// GET /incidents/{id} (04 §1): the senior with access details, the caregivers, the triggering
// event and every call from the first attempt until the incident was resolved.
@Serializable
data class IncidentPage(
    val id: String,
    val status: String,
    val reason: String,
    @SerialName("opened_at") val openedAt: String,
    @SerialName("taken_by_name") val takenByName: String? = null,
    @SerialName("handover_answered") val handoverAnswered: Boolean = false,
    val senior: IncidentSenior,
    val caregivers: List<IncidentCaregiver> = emptyList(),
    val event: TriggerEvent? = null,
    val calls: List<IncidentCall> = emptyList()
)

@Serializable
data class IncidentSenior(
    val id: String,
    @SerialName("full_name") val fullName: String,
    @SerialName("form_of_address") val formOfAddress: String,
    @SerialName("phone_e164") val phone: String,
    @SerialName("phone_is_landline") val landline: Boolean,
    val street: String? = null,
    @SerialName("street_number") val streetNumber: String? = null,
    val block: String? = null,
    val staircase: String? = null,
    val floor: String? = null,
    val apartment: String? = null,
    @SerialName("intercom_code") val intercomCode: String? = null,
    @SerialName("key_holder") val keyHolder: String? = null,
    val landmark: String? = null
)

// No user id here, unlike GET /seniors/{id}'s Caregiver.
@Serializable
data class IncidentCaregiver(
    @SerialName("display_name") val displayName: String,
    @SerialName("phone_e164") val phone: String,
    val relation: String? = null
)

@Serializable
data class TriggerEvent(
    val type: String,
    @SerialName("measured_at") val measuredAt: String,
    val latitude: Double? = null,
    val longitude: Double? = null,
    @SerialName("location_accuracy_m") val accuracy: Double? = null
)

// [handoverAnswered] is null when no hand-over was tried on this call.
@Serializable
data class IncidentCall(
    val id: String,
    val trigger: String,
    val attempt: Int,
    val state: String,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("final_severity") val finalSeverity: String? = null,
    @SerialName("handover_answered") val handoverAnswered: Boolean? = null,
    val reports: List<CallReport> = emptyList(),
    val turns: List<CallTurn> = emptyList(),
    // GET /calls/{id}/transcript only (04 §1); none on the incident page or from an older server
    val answers: List<CallAnswer> = emptyList()
)

// One answer the call heard (05 §2): [field] stays a string, so a question added later decodes.
@Serializable
data class CallAnswer(
    val field: String,
    val value: String,
    val clear: Boolean,
    val quote: String,
    val at: String
)

@Serializable
data class CallReport(
    val severity: String,
    val reason: String,
    val quote: String? = null,
    val at: String
)

// [kind] is `speech` or `keys`, a key press whose [content] is the key.
@Serializable
data class CallTurn(
    val speaker: String,
    val content: String,
    val at: String,
    val kind: String = "speech"
)

// POST /incidents/{id}/resolve's body (04 §2): both required, the note 1 to 1000 characters.
@Serializable
data class Resolution(val outcome: String, val note: String)

// The FastAPI contract (04-interfaces.md). One function per endpoint, added as features need them.
// Built in NetworkModule.
interface EchoCareApi {
    @GET("profile")
    suspend fun me(): Me

    /** The seniors the caller reaches as [role]; the server narrows the list (seniors SE6). */
    @GET("seniors")
    suspend fun seniors(@Query("role") role: String): List<SeniorRow>

    @GET("seniors/{id}")
    suspend fun senior(@Path("id") id: String): SeniorPage

    /** The senior's calls, newest first, queued ones included (04 §1). */
    @GET("seniors/{id}/calls")
    suspend fun calls(@Path("id") id: String): List<CallRow>

    /** A new senior in `draft`, registered by the calling medic (04 §2). Not repeat-safe (SE14). */
    @POST("seniors")
    suspend fun createSenior(@Body body: SeniorForm): SeniorPage

    /** The whole registration again, in any state (04 §2, SE9). */
    @PUT("seniors/{id}")
    suspend fun updateSenior(@Path("id") id: String, @Body body: SeniorForm): SeniorPage

    @POST("seniors/{id}/caregivers")
    suspend fun addCaregiver(@Path("id") id: String, @Body body: CaregiverForm): Caregiver

    /** 204, also on a repeat (04 §2). A Response, because a 204 has no body to decode. */
    @DELETE("seniors/{id}/caregivers/{userId}")
    suspend fun removeCaregiver(
        @Path("id") id: String,
        @Path("userId") userId: String
    ): Response<Unit>

    /** `draft` → `submitted`: DAS sees the senior from now on (04 §2). Answers one row. */
    @POST("seniors/{id}/submit")
    suspend fun submit(@Path("id") id: String): SeniorRow

    /** Queues the welcome call again; answers the senior's row (04 §2, UC-04). */
    @POST("seniors/{id}/welcome-call")
    suspend fun callAgain(@Path("id") id: String): SeniorRow

    /** Records that the senior withdrew her consent by phone; answers her row (04 §2). */
    @POST("seniors/{id}/consent-withdrawn")
    suspend fun withdraw(@Path("id") id: String): SeniorRow

    /** Stores the signed consent, 204 (04 §2). A Response, because a 204 has no body. */
    @POST("seniors/{id}/signature")
    suspend fun sign(@Path("id") id: String, @Body body: SignatureForm): Response<Unit>

    /** 200 with the due call, 204 with none, 404 on production (design §4.2). A 204 has no body. */
    @GET("profile/mock-call")
    suspend fun mockCall(): Response<MockCall>

    /** 204; a 409 means the call is no longer due (design §4.2). */
    @POST("calls/{id}/mock-answer")
    suspend fun mockAnswer(@Path("id") id: String, @Body body: MockAnswer): Response<Unit>

    /** Senior only. 200 also for a duplicate; [EventResult.callId] is null when no call was queued (04 §3). */
    @POST("me/events")
    suspend fun sendEvent(@Body body: EventForm): EventResult

    /** This device's push token, now the caller's (04 §6, Q19). 204, also on a repeat. */
    @PUT("profile/push-tokens/{token}")
    suspend fun savePushToken(@Path("token") token: String): Response<Unit>

    /** Forgets the caller's own token before signing out (Q19). 204 whether or not it was there. */
    @DELETE("profile/push-tokens/{token}")
    suspend fun dropPushToken(@Path("token") token: String): Response<Unit>

    /** DAS only. [status] is comma-separated; the DAS app asks for `open,in_progress` (04 §1). */
    @GET("incidents")
    suspend fun incidents(@Query("status") status: String): List<IncidentRow>

    @GET("incidents/{id}")
    suspend fun incident(@Path("id") id: String): IncidentPage

    /** One call's turns (04 §1): the incident page's call; its `answers` are ignored. */
    @GET("calls/{id}/transcript")
    suspend fun transcript(@Path("id") id: String): IncidentCall

    /** `open` → `in_progress` (UC-11). 409 `already_done` names who has it in `taken_by_name`. */
    @POST("incidents/{id}/take")
    suspend fun take(@Path("id") id: String): IncidentRow

    /** `in_progress` → `resolved`, by any DAS employee (UC-11). 409 `wrong_state` while open. */
    @POST("incidents/{id}/resolve")
    suspend fun resolve(@Path("id") id: String, @Body body: Resolution): IncidentRow
}
