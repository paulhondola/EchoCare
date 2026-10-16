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
@Serializable
data class Me(@SerialName("display_name") val displayName: String, val grants: List<Grant>)

@Serializable
data class Grant(val role: String)

// One row of GET /seniors (seniors §3.3). The state stays a string: a later server may add one.
@Serializable
data class SeniorRow(
    val id: String,
    @SerialName("full_name") val fullName: String,
    @SerialName("form_of_address") val formOfAddress: String,
    @SerialName("phone_e164") val phone: String,
    @SerialName("phone_is_landline") val landline: Boolean,
    @SerialName("enrollment_state") val state: String
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
}
