package bia.sentinela

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.GET
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

// The FastAPI contract (04-interfaces.md). One function per endpoint, added as features need them.
// Built in NetworkModule.
interface SentinelaApi {
    @GET("me")
    suspend fun me(): Me

    /** The seniors the caller reaches as [role]; the server narrows the list (seniors SE6). */
    @GET("seniors")
    suspend fun seniors(@Query("role") role: String): List<SeniorRow>

    @GET("seniors/{id}")
    suspend fun senior(@Path("id") id: String): SeniorPage
}
