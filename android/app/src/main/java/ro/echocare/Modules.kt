package ro.echocare

import com.google.android.gms.tasks.Tasks
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseUser
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import java.io.IOException
import java.util.concurrent.ExecutionException
import javax.inject.Singleton
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.create

@Module
@InstallIn(SingletonComponent::class)
object FirebaseModule {
    @Provides
    @Singleton
    fun firebaseAuth(): FirebaseAuth = FirebaseAuth.getInstance().apply {
        // Affects only Firebase's test numbers: emulators sign in before the SHA fingerprints
        // are registered (auth-layer §8.2, §9 step 1). Real numbers need verification on, so
        // echocare.realSms=true in local.properties leaves it on in a debug build.
        if (!BuildConfig.REAL_SMS) firebaseAuthSettings.setAppVerificationDisabledForTesting(true)
    }
}

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    // An old APK will talk to a newer API: ignore fields this build does not know (ADR-001 §2.3).
    private val json = Json { ignoreUnknownKeys = true }

    // ponytail: OkHttp and Retrofit are built here, not provided, until a second API needs them.
    @Provides
    @Singleton
    fun echoCareApi(auth: FirebaseAuth): EchoCareApi {
        val client = OkHttpClient.Builder()
            // The Firebase token goes in one interceptor (app/AGENTS.md). Runs on OkHttp's thread.
            .addInterceptor { chain ->
                val user = auth.currentUser ?: return@addInterceptor chain.proceed(chain.request())
                chain.proceed(
                    chain.request().newBuilder().header("Authorization", user.bearer(false)).build()
                )
            }
            // A 401 retries once with a forced-fresh token; a second 401 reaches the caller (auth-layer §3.2).
            .authenticator { _, response ->
                val user = auth.currentUser
                if (response.priorResponse != null || user == null) {
                    null
                } else {
                    response.request.newBuilder().header("Authorization", user.bearer(true)).build()
                }
            }
            .build()
        return Retrofit.Builder()
            // Every FastAPI route is under /api; API_URL is the bare origin. Retrofit requires the trailing slash.
            .baseUrl(BuildConfig.API_URL + "/api/")
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create()
    }

    // OkHttp turns only an IOException into a failed call; anything else crashes its thread.
    private fun FirebaseUser.bearer(forceRefresh: Boolean): String = try {
        "Bearer " + Tasks.await(getIdToken(forceRefresh)).token
    } catch (e: ExecutionException) {
        throw IOException("Firebase token unavailable", e)
    }
}
