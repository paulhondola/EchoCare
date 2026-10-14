package bia.sentinela

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import bia.sentinela.auth.AuthViewModel
import bia.sentinela.auth.Screen
import bia.sentinela.auth.toE164
import bia.sentinela.home.HomeNav
import bia.sentinela.ui.Kind
import bia.sentinela.ui.Rule
import bia.sentinela.ui.SnButton
import bia.sentinela.ui.SnTextField
import bia.sentinela.ui.theme.Palette
import bia.sentinela.ui.theme.SentinelaTheme
import com.google.firebase.FirebaseException
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.PhoneAuthCredential
import com.google.firebase.auth.PhoneAuthOptions
import com.google.firebase.auth.PhoneAuthProvider
import dagger.hilt.android.AndroidEntryPoint
import java.util.concurrent.TimeUnit
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    @Inject lateinit var auth: FirebaseAuth

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // One dark theme (spec 07 §2.1): light status and navigation icons whatever the system uses
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT)
        )
        setContent {
            val vm: AuthViewModel = hiltViewModel()
            SentinelaTheme {
                when (val screen = vm.screen) {
                    // Signed in: the role's home and what opens from it (seniors §8.2).
                    is Screen.Home -> HomeNav(
                        screen,
                        onSwitchRole = vm::switchRole,
                        onSignOut = vm::signOut,
                        onSessionEnd = vm::sessionEnded
                    )

                    else -> Scaffold(
                        modifier = Modifier.fillMaxSize(),
                        containerColor = Palette.Canvas
                    ) { innerPadding ->
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

    // PhoneAuthOptions needs an Activity for the reCAPTCHA fallback, so verification starts here
    // and the ViewModel only receives the results (auth-layer §8.2).
    private fun sendCode(
        vm: AuthViewModel,
        phone: String,
        resend: PhoneAuthProvider.ForceResendingToken?
    ) {
        vm.sending(phone)
        val options = PhoneAuthOptions.newBuilder(auth)
            .setPhoneNumber(phone)
            .setTimeout(60L, TimeUnit.SECONDS)
            .setActivity(this)
            .setCallbacks(
                object : PhoneAuthProvider.OnVerificationStateChangedCallbacks() {
                    // Automatic SMS reading: sign in straight away.
                    override fun onVerificationCompleted(credential: PhoneAuthCredential) =
                        vm.signIn(credential)

                    override fun onVerificationFailed(e: FirebaseException) =
                        vm.verificationFailed(e)

                    override fun onCodeSent(
                        id: String,
                        token: PhoneAuthProvider.ForceResendingToken
                    ) = vm.codeSent(id, token)
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
        Text(
            stringResource(R.string.app_name).uppercase(),
            style = MaterialTheme.typography.titleLarge
        )
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
