package ro.echocare.auth

import android.content.Context
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.edit
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.firebase.FirebaseException
import com.google.firebase.FirebaseTooManyRequestsException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.FirebaseAuthException
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
private const val TAG = "EchoCareAuth"

/**
 * Firebase's own reason for a failed sign-in step, for `adb logcat -s EchoCareAuth`. The screen
 * shows only a short Romanian text (auth-layer §3.2), which hides codes such as `Error code:39`.
 */
private fun logFailure(step: String, e: FirebaseException) {
    val code = (e as? FirebaseAuthException)?.errorCode
    Log.w(TAG, "$step failed: ${e.javaClass.simpleName} ${code.orEmpty()} ${e.message}", e)
}

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

    var screen by mutableStateOf<Screen>(Screen.Landing)
        private set

    /** *Retrimite codul* opens 30 seconds after a code is sent (auth-layer §8.2). */
    var canResend by mutableStateOf(false)
        private set

    /** The E.164 number the code went to, and Firebase's token for resending to it. */
    var phone = ""
        private set
    var resendToken: PhoneAuthProvider.ForceResendingToken? = null
        private set

    /**
     * Firebase can't cancel a verification, so each code sent, and each step back to the landing,
     * starts a new attempt: the Activity drops callbacks from an older one.
     */
    var attempt = 0
        private set

    private lateinit var verificationId: String
    private lateinit var me: Me
    private var resendTimer: Job? = null

    init {
        // Signed out with no network, the token outlives the sign-out: deleted once one is back.
        // ponytail: until then, a closed app still shows the tray's alert, which names nobody (P18).
        // A WorkManager job if a device can stay offline and signed out for long.
        if (auth.currentUser != null) loadMe() else messaging.deleteToken()
    }

    /** *Intrați* on the landing page. */
    fun openSignIn() {
        screen = Screen.Phone()
    }

    /** Back from the phone or code step, before anyone is signed in. */
    fun backToLanding() {
        attempt++
        screen = Screen.Landing
    }

    /** Returns the new attempt, for the Activity to compare its callbacks against. */
    fun sending(phone: String): Int {
        this.phone = phone
        screen = Screen.Loading
        return ++attempt
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
        logFailure("Sending the code", e)
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
                logFailure("Signing in with the code", e)
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
        show(Screen.Home(role, me.displayName, rolesOf(me)))
    }

    /**
     * *Ieșire*. The API forgets this device's token first, while the caller is still signed in to
     * say whose it is (Q19). Offline, neither that nor the delete in [show] gets through: the next
     * start tries the delete again.
     */
    fun signOut() {
        screen = Screen.Loading
        viewModelScope.launch {
            withTimeoutOrNull(5.seconds) {
                try {
                    api.dropPushToken(messaging.token.await())
                } catch (e: Exception) {
                    // IOException, an HTTP refusal or no token: the delete in [show] still follows
                    if (e is CancellationException) throw e
                }
            }
            show(Screen.Landing)
        }
    }

    /**
     * A read after sign-in was refused as signed out or not registered (seniors §8.2): a grant
     * revoked mid-session ends the session, with the not-registered text. Signed out, it opens the
     * phone form rather than the landing, as a 401 from /me does: this person was just signed in.
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
            is Screen.Phone, Screen.NotRegistered, Screen.Landing -> {
                auth.signOut()
                prefs.edit { remove(SAVED_ROLE) }
                // Firebase forgets the token, so pushes stop; the next sign-in saves a new one
                messaging.deleteToken()
            }
            // A saved role that is no longer among the grants is dropped (auth-layer §8.2).
            is Screen.PickRole -> prefs.edit { remove(SAVED_ROLE) }
            else -> {}
        }
        screen = next
    }
}
