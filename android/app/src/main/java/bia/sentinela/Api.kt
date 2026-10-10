package bia.sentinela

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.create
import retrofit2.http.GET

@Serializable
data class Health(val status: String, val env: String)

// The FastAPI contract (04-interfaces.md). One function per endpoint, added as features need them.
interface SentinelaApi {
    @GET("health")
    suspend fun health(): Health
}

object Api {
    // An old APK will talk to a newer API: ignore fields this build does not know (ADR-001 §2.3).
    private val json = Json { ignoreUnknownKeys = true }

    val sentinela: SentinelaApi = Retrofit.Builder()
        // Every FastAPI route is under /api; API_URL is the bare origin. Retrofit requires the trailing slash.
        .baseUrl(BuildConfig.API_URL + "/api/")
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()
        .create()
}
