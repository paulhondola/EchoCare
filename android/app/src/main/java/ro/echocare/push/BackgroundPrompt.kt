package ro.echocare.push

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import ro.echocare.R
import ro.echocare.ui.Kind
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone

private fun unrestricted(context: Context): Boolean =
    context.getSystemService(PowerManager::class.java)
        .isIgnoringBatteryOptimizations(context.packageName)

/**
 * Asks, on the senior's own page, that the app may run in the background (G5): the phone is the
 * watch's only route to FastAPI, and a phone that puts the app to sleep drops its check-ins and
 * events without a word. Gone once allowed.
 */
@SuppressLint("BatteryLife") // the app relays a health monitor's events, an allowed use
@Composable
fun BackgroundPrompt() {
    val context = LocalContext.current
    var allowed by remember { mutableStateOf(unrestricted(context)) }
    // Back from the system dialog
    LifecycleResumeEffect(Unit) {
        allowed = unrestricted(context)
        onPauseOrDispose {}
    }
    if (allowed) return
    Column(
        Modifier
            .fillMaxWidth()
            .background(Tone.Galben.fill)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text(
            stringResource(R.string.background_off),
            color = Tone.Galben.text,
            style = MaterialTheme.typography.bodyMedium
        )
        SnButton(
            stringResource(R.string.background_on),
            {
                context.startActivity(
                    Intent(
                        Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:${context.packageName}")
                    )
                )
            },
            kind = Kind.Outline
        )
    }
}
