package bia.sentinela

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.GET

// GET /me (auth-layer §3.3). Only the fields the app reads; roles stay strings (ADR-001 §2.3).
@Serializable
data class Me(@SerialName("display_name") val displayName: String, val grants: List<Grant>)

@Serializable
data class Grant(val role: String)

// The FastAPI contract (04-interfaces.md). One function per endpoint, added as features need them.
// Built in NetworkModule.
interface SentinelaApi {
    @GET("me")
    suspend fun me(): Me
}
