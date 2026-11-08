package ro.echocare.wear.presentation

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.health.connect.HealthPermissions
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import java.time.Instant
import java.util.UUID
import ro.echocare.shared.EventMessage
import ro.echocare.wear.BuildConfig
import ro.echocare.wear.R
import ro.echocare.wear.monitoring.MonitoringService

private val REQUESTED_PERMISSIONS = arrayOf(
    HealthPermissions.READ_HEART_RATE,
    Manifest.permission.ACTIVITY_RECOGNITION,
    Manifest.permission.POST_NOTIFICATIONS
)

private fun Context.hasSensorPermissions() = REQUESTED_PERMISSIONS.all {
    checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED
}

/**
 * The senior's watch home (UC-09, UC-10): asks for the sensor permissions, starts
 * `MonitoringService` and shows a „Sunați-mă" button that reaches FastAPI through the phone.
 * `MainActivity` swaps in `AreYouOkScreen` when `MonitoringService.fallPrompt` is non-null.
 */
@Composable
fun SeniorHomeScreen() {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(context.hasSensorPermissions()) }
    val request = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        granted = context.hasSensorPermissions()
        if (granted && !MonitoringService.running.value) MonitoringService.start(context)
    }
    LaunchedEffect(Unit) {
        if (!granted) {
            request.launch(REQUESTED_PERMISSIONS)
        } else if (!MonitoringService.running.value) {
            MonitoringService.start(context)
        }
    }

    val monitoring by MonitoringService.running.collectAsState()
    var sending by remember { mutableStateOf(false) }

    val listState = rememberTransformingLazyColumnState()
    ScreenScaffold(scrollState = listState) { contentPadding ->
        TransformingLazyColumn(contentPadding = contentPadding, state = listState) {
            item { ListHeader { Text(stringResource(R.string.app_name)) } }
            if (!granted) {
                item { Line(stringResource(R.string.permission_needed)) }
                item {
                    Button(
                        onClick = { request.launch(REQUESTED_PERMISSIONS) },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text(stringResource(R.string.grant_permission)) }
                }
            } else {
                item {
                    Text(
                        stringResource(
                            if (monitoring) R.string.monitor_active else R.string.monitor_off
                        ),
                        modifier = Modifier.fillMaxWidth(),
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.bodyLarge
                    )
                }
                item {
                    Button(
                        onClick = {
                            if (sending) return@Button
                            sending = true
                            sendManualRequest(context) { sending = false }
                        },
                        enabled = !sending,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(
                            stringResource(
                                if (sending) R.string.call_me_sending else R.string.call_me
                            )
                        )
                    }
                }
                if (BuildConfig.DEBUG) {
                    item {
                        Button(
                            onClick = {
                                MonitoringService.forceAnomaly(context, "high_pulse_at_rest")
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text(stringResource(R.string.force_high_pulse)) }
                    }
                    item {
                        Button(
                            onClick = { MonitoringService.forceAnomaly(context, "inactivity") },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text(stringResource(R.string.force_inactivity)) }
                    }
                    item {
                        Button(
                            onClick = { MonitoringService.forceAnomaly(context, "fall") },
                            modifier = Modifier.fillMaxWidth()
                        ) { Text(stringResource(R.string.force_fall)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun Line(text: String) {
    Text(text, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
}

private fun sendManualRequest(context: Context, onDone: () -> Unit) {
    MonitoringService.sendEvent(
        context,
        EventMessage(
            id = UUID.randomUUID().toString(),
            type = "manual_request",
            measuredAt = Instant.now().toString()
        )
    )
    onDone()
}
