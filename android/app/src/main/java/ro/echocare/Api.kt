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
    val since: String? = null
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
    val caregivers: List<Caregiver> = emptyList()
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
    val turns: List<CallTurn> = emptyList()
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

    /** A new senior in `draft`, registered by the calling medic (04 §2). Not repeat-safe (SE14). */
    @POST("seniors")
    suspend fun createSenior(@Body body: SeniorForm): SeniorPage

    /** The whole registration again, while `draft` or `submitted` (04 §2). */
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

    /** 200 with the due call, 204 with none, 404 on production (design §4.2). A 204 has no body. */
    @GET("profile/mock-call")
    suspend fun mockCall(): Response<MockCall>

    /** 204; a 409 means the call is no longer due (design §4.2). */
    @POST("calls/{id}/mock-answer")
    suspend fun mockAnswer(@Path("id") id: String, @Body body: MockAnswer): Response<Unit>

    /** DAS only. [status] is comma-separated; the DAS app asks for `open,in_progress` (04 §1). */
    @GET("incidents")
    suspend fun incidents(@Query("status") status: String): List<IncidentRow>

    @GET("incidents/{id}")
    suspend fun incident(@Path("id") id: String): IncidentPage

    /** `open` → `in_progress` (UC-11). 409 `already_done` names who has it in `taken_by_name`. */
    @POST("incidents/{id}/take")
    suspend fun take(@Path("id") id: String): IncidentRow

    /** `in_progress` → `resolved`, by any DAS employee (UC-11). 409 `wrong_state` while open. */
    @POST("incidents/{id}/resolve")
    suspend fun resolve(@Path("id") id: String, @Body body: Resolution): IncidentRow
}
