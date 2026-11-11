package ro.echocare

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import com.google.firebase.FirebaseException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.PhoneAuthCredential
import com.google.firebase.auth.PhoneAuthOptions
import com.google.firebase.auth.PhoneAuthProvider
import dagger.hilt.android.AndroidEntryPoint
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import ro.echocare.auth.AuthViewModel
import ro.echocare.auth.Landing
import ro.echocare.auth.Screen
import ro.echocare.auth.toE164
import ro.echocare.home.HomeNav
import ro.echocare.push.PUSH_KEYS
import ro.echocare.push.Push
import ro.echocare.push.pushFrom
import ro.echocare.ui.Kind
import ro.echocare.ui.Rule
import ro.echocare.ui.SnButton
import ro.echocare.ui.SnTextField
import ro.echocare.ui.theme.EchoCareTheme
import ro.echocare.ui.theme.Palette

/** Saved across a rotation: no alert is waiting to open. */
private const val ALERT_OPENED = "alert_opened"

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject lateinit var auth: FirebaseAuth

    /** A tapped alert to open once the role's home is shown (04 §6); null when there is none. */
    private var opening by mutableStateOf<Push.Alert?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Not again after a rotation, once opened: its page is on the back stack already
        if (savedInstanceState?.getBoolean(ALERT_OPENED) != true) opening = alertIn(intent)
        // One dark theme (spec 07 §2.1): light status and navigation icons whatever the system uses
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT)
        )
        setContent {
            val vm: AuthViewModel = hiltViewModel()
            EchoCareTheme {
                when (val screen = vm.screen) {
                    // Signed in: the role's home and what opens from it (seniors §8.2).
                    is Screen.Home -> HomeNav(
                        screen,
                        onSwitchRole = vm::switchRole,
                        onSignOut = vm::signOut,
                        onSessionEnd = vm::sessionEnded,
                        opening = opening,
                        onOpened = { opening = null }
                    )

                    else -> Scaffold(
                        modifier = Modifier.fillMaxSize(),
                        containerColor = Palette.Canvas
                    ) { innerPadding ->
                        if (screen == Screen.Landing) {
                            Landing(vm::openSignIn, Modifier.padding(innerPadding))
                            return@Scaffold
                        }
                        SignIn(
                            vm,
                            onSendCode = { sendCode(vm, it, null) },
                            onResend = { sendCode(vm, vm.phone, vm.resendToken) },
                            modifier = Modifier.padding(innerPadding)
                        )
                    }
                }
            }
        }
    }

    /** A tap on an alert while the app is open: singleTop brings it here (04 §6). */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        alertIn(intent)?.let {
            opening = it
            // So a rotation before it opens, while the sign-in loads, still finds it
            setIntent(intent)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean(ALERT_OPENED, opening == null)
    }

    /** The alert a notification tap carries, from the tray or from [ro.echocare.push.showAlert]. */
    private fun alertIn(intent: Intent?): Push.Alert? {
        val extras = intent?.extras ?: return null
        return pushFrom(PUSH_KEYS.associateWith { extras.getString(it) }) as? Push.Alert
    }

    // PhoneAuthOptions needs an Activity for the reCAPTCHA fallback, so verification starts here
    // and the ViewModel only receives the results (auth-layer §8.2).
    private fun sendCode(
        vm: AuthViewModel,
        phone: String,
        resend: PhoneAuthProvider.ForceResendingToken?
    ) {
        val attempt = vm.sending(phone)

        // Late callbacks from an attempt left with Înapoi, or replaced by a resend, change nothing
        fun current() = attempt == vm.attempt
        val options = PhoneAuthOptions.newBuilder(auth)
            .setPhoneNumber(phone)
            .setTimeout(60L, TimeUnit.SECONDS)
            .setActivity(this)
            .setCallbacks(
                object : PhoneAuthProvider.OnVerificationStateChangedCallbacks() {
                    // Automatic SMS reading: sign in straight away.
                    override fun onVerificationCompleted(credential: PhoneAuthCredential) {
                        if (current()) vm.signIn(credential)
                    }

                    override fun onVerificationFailed(e: FirebaseException) {
                        if (current()) vm.verificationFailed(e)
                    }

                    override fun onCodeSent(
                        id: String,
                        token: PhoneAuthProvider.ForceResendingToken
                    ) {
                        if (current()) vm.codeSent(id, token)
                    }
                }
            )
        resend?.let(options::setForceResendingToken)
        PhoneAuthProvider.verifyPhoneNumber(options.build())
    }
}

private val ROLE_LABELS = mapOf(
    "das" to R.string.role_das,
    "medic" to R.string.role_medic,
    "caregiver" to R.string.role_caregiver,
    "senior" to R.string.role_senior
)

@Composable
fun SignIn(
    vm: AuthViewModel,
    onSendCode: (String) -> Unit,
    onResend: () -> Unit,
    modifier: Modifier = Modifier
) {
    Box(modifier.fillMaxSize().padding(16.dp), contentAlignment = Alignment.Center) {
        when (val screen = vm.screen) {
            Screen.Loading -> CircularProgressIndicator(color = Palette.FgMuted)
            // Shown by HomeNav in MainActivity, not here.
            is Screen.Home -> {}
            else -> Panel {
                // Before anyone is signed in, back returns to the landing page
                val beforeSignIn =
                    screen is Screen.Phone ||
                        screen is Screen.Code ||
                        screen == Screen.NotRegistered
                BackHandler(enabled = beforeSignIn, onBack = vm::backToLanding)
                when (screen) {
                    is Screen.Phone -> PhoneForm(screen.error, onSendCode)
                    // Signed out already: the phone form, under the not-registered text (auth-layer §3.2).
                    Screen.NotRegistered -> PhoneForm(R.string.not_registered, onSendCode)
                    is Screen.Code -> CodeForm(screen.error, vm.canResend, vm::submitCode, onResend)
                    Screen.Unavailable -> {
                        ErrorText(R.string.unavailable)
                        SnButton(
                            stringResource(R.string.retry),
                            vm::loadMe,
                            Modifier.fillMaxWidth(),
                            kind = Kind.Link
                        )
                        SnButton(
                            stringResource(R.string.sign_out),
                            vm::signOut,
                            Modifier.fillMaxWidth(),
                            kind = Kind.Outline
                        )
                    }
                    is Screen.PickRole -> {
                        Title(R.string.pick_role_title)
                        screen.roles.forEach { role ->
                            SnButton(
                                stringResource(ROLE_LABELS.getValue(role)),
                                { vm.pickRole(role) },
                                Modifier.fillMaxWidth()
                            )
                        }
                    }
                    else -> {}
                }
                if (beforeSignIn) {
                    SnButton(
                        stringResource(R.string.back),
                        vm::backToLanding,
                        Modifier.fillMaxWidth(),
                        kind = Kind.Outline
                    )
                }
            }
        }
    }
}

/** The dashboard's sign-in panel: the brand, a 2dp rule, then the step. */
@Composable
private fun Panel(content: @Composable () -> Unit) {
    Column(
        Modifier
            .widthIn(max = 420.dp)
            .fillMaxWidth()
            .border(2.dp, Palette.Line)
            .background(Palette.Subtle)
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Image(
                painterResource(R.drawable.ic_brand),
                contentDescription = null,
                modifier = Modifier.size(32.dp)
            )
            Text(
                stringResource(R.string.app_name).uppercase(),
                style = MaterialTheme.typography.titleLarge
            )
        }
        Rule()
        content()
    }
}

@Composable
private fun Title(text: Int) {
    Text(stringResource(text), style = MaterialTheme.typography.headlineSmall)
}

@Composable
private fun ErrorText(text: Int) {
    Text(stringResource(text), color = Palette.RosuFg, style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun PhoneForm(error: Int?, onSendCode: (String) -> Unit) {
    var phone by rememberSaveable { mutableStateOf("") }
    Title(R.string.sign_in_title)
    SnTextField(phone, { phone = it }, stringResource(R.string.phone_label), KeyboardType.Phone)
    error?.let { ErrorText(it) }
    SnButton(
        stringResource(R.string.send_code),
        { onSendCode(toE164(phone)) },
        Modifier.fillMaxWidth(),
        kind = Kind.Link,
        enabled = phone.isNotBlank()
    )
}

@Composable
private fun CodeForm(
    error: Int?,
    canResend: Boolean,
    onConfirm: (String) -> Unit,
    onResend: () -> Unit
) {
    var code by rememberSaveable { mutableStateOf("") }
    Title(R.string.sign_in_title)
    SnTextField(
        value = code,
        onValueChange = { code = it },
        label = stringResource(R.string.code_label),
        keyboardType = KeyboardType.NumberPassword
    )
    error?.let { ErrorText(it) }
    SnButton(
        stringResource(R.string.confirm),
        { onConfirm(code) },
        Modifier.fillMaxWidth(),
        kind = Kind.Success,
        enabled = code.isNotBlank()
    )
    SnButton(
        stringResource(R.string.resend_code),
        onResend,
        Modifier.fillMaxWidth(),
        kind = Kind.Outline,
        enabled = canResend
    )
}
