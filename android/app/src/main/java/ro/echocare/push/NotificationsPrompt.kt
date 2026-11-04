package ro.echocare.push

import android.Manifest
import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.runtime.saveable.rememberSaveable
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

/**
 * Asks for notifications on the home of a role that gets alerts (04 §6), in Romanian, before the
 * system's own dialog: the first tap opens that dialog, a later one, after a refusal, the app's
 * notification settings, since Android stops asking. Gone once they are allowed.
 */
@Composable
fun NotificationsPrompt() {
    val context = LocalContext.current
    var allowed by remember { mutableStateOf(notificationsAllowed(context)) }
    var asked by rememberSaveable { mutableStateOf(false) }
    // Back from the settings, or from the system dialog
    LifecycleResumeEffect(Unit) {
        allowed = notificationsAllowed(context)
        onPauseOrDispose {}
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        allowed = it
        asked = true
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
            stringResource(R.string.notifications_off),
            color = Tone.Galben.text,
            style = MaterialTheme.typography.bodyMedium
        )
        SnButton(
            stringResource(R.string.notifications_on),
            {
                if (asked) {
                    context.startActivity(
                        Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                            .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                    )
                } else {
                    ask.launch(Manifest.permission.POST_NOTIFICATIONS)
                }
            },
            kind = Kind.Outline
        )
    }
}
