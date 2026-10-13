package bia.sentinela

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
        enableEdgeToEdge()
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

                    else -> Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
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
    Box(modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        when (val screen = vm.screen) {
            is Screen.Phone -> PhoneForm(screen.error, onSendCode)
            // Signed out already: the phone form, under the not-registered text (auth-layer §3.2).
            Screen.NotRegistered -> PhoneForm(R.string.not_registered, onSendCode)
            is Screen.Code -> CodeForm(screen.error, vm.canResend, vm::submitCode, onResend)
            Screen.Loading -> CircularProgressIndicator()
            Screen.Unavailable -> Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(stringResource(R.string.unavailable))
                Button(vm::loadMe) { Text(stringResource(R.string.retry)) }
                TextButton(vm::signOut) { Text(stringResource(R.string.sign_out)) }
            }
            is Screen.PickRole -> Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(
                    stringResource(R.string.pick_role_title),
                    style = MaterialTheme.typography.headlineMedium
                )
                screen.roles.forEach { role ->
                    Button({ vm.pickRole(role) }, Modifier.fillMaxWidth()) {
                        Text(stringResource(ROLE_LABELS.getValue(role)))
                    }
                }
            }
            // Shown by HomeNav in MainActivity, not here.
            is Screen.Home -> {}
        }
    }
}

@Composable
private fun PhoneForm(error: Int?, onSendCode: (String) -> Unit) {
    var phone by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(
            stringResource(R.string.sign_in_title),
            style = MaterialTheme.typography.headlineMedium
        )
        OutlinedTextField(
            phone,
            { phone = it },
            label = { Text(stringResource(R.string.phone_label)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            singleLine = true
        )
        error?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error) }
        Button(onClick = { onSendCode(toE164(phone)) }, enabled = phone.isNotBlank()) {
            Text(stringResource(R.string.send_code))
        }
    }
}

@Composable
private fun CodeForm(
    error: Int?,
    canResend: Boolean,
    onConfirm: (String) -> Unit,
    onResend: () -> Unit
) {
    var code by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        OutlinedTextField(
            code,
            { code = it },
            label = { Text(stringResource(R.string.code_label)) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            singleLine = true
        )
        error?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error) }
        Button(onClick = { onConfirm(code) }, enabled = code.isNotBlank()) {
            Text(stringResource(R.string.confirm))
        }
        TextButton(onResend, enabled = canResend) { Text(stringResource(R.string.resend_code)) }
    }
}
