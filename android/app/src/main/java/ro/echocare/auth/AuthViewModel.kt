package ro.echocare.auth

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.edit
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.firebase.FirebaseException
import com.google.firebase.FirebaseTooManyRequestsException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthInvalidCredentialsException
import com.google.firebase.auth.PhoneAuthCredential
import com.google.firebase.auth.PhoneAuthProvider
import com.google.firebase.messaging.FirebaseMessaging
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.IOException
import javax.inject.Inject
import kotlin.coroutines.cancellation.CancellationException
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeoutOrNull
import retrofit2.HttpException
import ro.echocare.EchoCareApi
import ro.echocare.Me
import ro.echocare.R
import ro.echocare.home.Failure

private const val SAVED_ROLE = "role"

/**
 * Phone sign-in, then GET /me (auth-layer §8.2, UC-02). The Activity starts phone verification,
 * because PhoneAuthOptions needs an Activity, and passes the callbacks' results in here.
 */
@HiltViewModel
class AuthViewModel @Inject constructor(
    private val auth: FirebaseAuth,
    private val api: EchoCareApi,
    private val messaging: FirebaseMessaging,
    @ApplicationContext context: Context
) : ViewModel() {
    // The picked role survives a restart (auth-layer §8.2).
    private val prefs = context.getSharedPreferences("auth", Context.MODE_PRIVATE)

    var screen by mutableStateOf<Screen>(Screen.Phone())
        private set

    /** *Retrimite codul* opens 30 seconds after a code is sent (auth-layer §8.2). */
    var canResend by mutableStateOf(false)
        private set

    /** The E.164 number the code went to, and Firebase's token for resending to it. */
    var phone = ""
        private set
    var resendToken: PhoneAuthProvider.ForceResendingToken? = null
        private set

    private lateinit var verificationId: String
    private lateinit var me: Me
    private var resendTimer: Job? = null

    init {
        if (auth.currentUser != null) loadMe()
    }

    fun sending(phone: String) {
        this.phone = phone
        screen = Screen.Loading
    }

    fun codeSent(id: String, token: PhoneAuthProvider.ForceResendingToken) {
        verificationId = id
        resendToken = token
        screen = Screen.Code()
        canResend = false
        resendTimer?.cancel()
        resendTimer = viewModelScope.launch {
            delay(30.seconds)
            canResend = true
        }
    }

    fun verificationFailed(e: FirebaseException) {
        screen = Screen.Phone(
            when (e) {
                is FirebaseAuthInvalidCredentialsException -> R.string.invalid_phone
                is FirebaseTooManyRequestsException -> R.string.too_many_attempts
                else -> R.string.unavailable
            }
        )
    }

    fun submitCode(code: String) = signIn(PhoneAuthProvider.getCredential(verificationId, code))

    /** From the typed code, or from `onVerificationCompleted` when the SMS was read automatically. */
    fun signIn(credential: PhoneAuthCredential) {
        screen = Screen.Loading
        viewModelScope.launch {
            try {
                auth.signInWithCredential(credential).await()
            } catch (e: FirebaseException) {
                val wrong = e is FirebaseAuthInvalidCredentialsException
                screen = Screen.Code(if (wrong) R.string.wrong_code else R.string.unavailable)
                return@launch
            }
            loadMe()
        }
    }

    fun loadMe() {
        screen = Screen.Loading
        viewModelScope.launch {
            show(
                try {
                    me = api.me()
                    savePushToken()
                    screenFor(me, prefs.getString(SAVED_ROLE, null))
                } catch (e: HttpException) {
                    screenFor(e.code())
                } catch (e: IOException) {
                    Screen.Unavailable
                }
            )
        }
    }

    fun pickRole(role: String) {
        prefs.edit { putString(SAVED_ROLE, role) }
        show(Screen.Home(role, me.displayName, canSwitch = true))
    }

    /** *Schimbă rolul*: back to the picker, forgetting the saved role. */
    fun switchRole() = show(screenFor(me, saved = null))

    /**
     * *Ieșire*. The API forgets this device's token first, while the caller is still signed in to
     * say whose it is (Q19); offline, the token is deleted on the device anyway, in [show].
     */
    fun signOut() {
        screen = Screen.Loading
        viewModelScope.launch {
            withTimeoutOrNull(5.seconds) {
                try {
                    api.dropPushToken(messaging.token.await())
                } catch (e: Exception) {
                    // IOException, an HTTP refusal or no token: the device's own delete still holds
                    if (e is CancellationException) throw e
                }
            }
            show(Screen.Phone())
        }
    }

    /**
     * A read after sign-in was refused as signed out or not registered (seniors §8.2): a grant
     * revoked mid-session ends the session, with the not-registered text.
     */
    fun sessionEnded(failure: Failure) =
        show(if (failure == Failure.NotRegistered) Screen.NotRegistered else Screen.Phone())

    /** Every start and sign-in, so the API always holds this device's current token (04 §6). */
    private fun savePushToken() {
        viewModelScope.launch {
            try {
                api.savePushToken(messaging.token.await())
            } catch (e: Exception) {
                // Offline or refused: tried again at the next start, or on a new token
                if (e is CancellationException) throw e
            }
        }
    }

    private fun show(next: Screen) {
        when (next) {
            // auth-layer §3.2: not_registered and a second 401 sign out of Firebase.
            is Screen.Phone, Screen.NotRegistered -> {
                auth.signOut()
                prefs.edit { remove(SAVED_ROLE) }
                // No pushes reach a signed-out device; the next sign-in saves a new token
                messaging.deleteToken()
            }
            // A saved role that is no longer among the grants is dropped (auth-layer §8.2).
            is Screen.PickRole -> prefs.edit { remove(SAVED_ROLE) }
            else -> {}
        }
        screen = next
    }
}
