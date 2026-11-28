package ro.echocare.wear.presentation

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.health.connect.HealthPermissions
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.IconButton
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import java.time.Instant
import java.util.UUID
import ro.echocare.shared.EventMessage
import ro.echocare.wear.BuildConfig
import ro.echocare.wear.R
import ro.echocare.wear.monitoring.MonitoringService
import ro.echocare.wear.presentation.theme.Palette

private val REQUESTED_PERMISSIONS = arrayOf(
    HealthPermissions.READ_HEART_RATE,
    Manifest.permission.ACTIVITY_RECOGNITION,
    Manifest.permission.POST_NOTIFICATIONS
)

private fun Context.hasSensorPermissions() = REQUESTED_PERMISSIONS.all {
    checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED
}

/**
 * The senior's watch home (UC-09, UC-10), redesigned for seniors like the Apple Watch's
 * `HomeView.swift` (design 2026-11-14, watch senior UI): a calm status at a glance, the pulse, and
 * one big red „Nu mă simt bine”, which reaches FastAPI through the phone. The small pause button at
 * the top is the team's toggle. Debug builds add the synthetic-anomaly buttons below the fold.
 * `MainActivity` swaps in `AreYouOkScreen` and `HelpComingScreen`.
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
    val bpm by MonitoringService.heartRate.collectAsState()

    val listState = rememberTransformingLazyColumnState()
    ScreenScaffold(scrollState = listState) { contentPadding ->
        TransformingLazyColumn(contentPadding = contentPadding, state = listState) {
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
                    val label = stringResource(
                        if (monitoring) R.string.stop_monitoring else R.string.start_monitoring
                    )
                    // A round screen clips the corners, so the toggle sits at the top centre
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        IconButton(
                            onClick = {
                                if (monitoring) {
                                    MonitoringService.stop(context)
                                } else {
                                    MonitoringService.start(context)
                                }
                            },
                            modifier = Modifier
                                .size(32.dp)
                                .semantics { contentDescription = label }
                        ) {
                            Text(if (monitoring) "❚❚" else "▶", color = Color.Gray)
                        }
                    }
                }
            }
            item {
                Text(
                    "♥",
                    modifier = Modifier
                        .fillMaxWidth()
                        .clearAndSetSemantics {},
                    textAlign = TextAlign.Center,
                    fontSize = 44.sp,
                    color = if (monitoring) Palette.Calm else Color.Gray
                )
            }
            item {
                Text(
                    stringResource(if (monitoring) R.string.all_good else R.string.monitor_off),
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
            }
            if (monitoring) {
                item {
                    val b = bpm
                    Line(
                        if (b == null) {
                            stringResource(R.string.heart_rate_waiting)
                        } else {
                            stringResource(R.string.heart_rate_plain, b)
                        },
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            // Works whether monitoring runs or not: sending an event starts the service if needed
            item {
                Button(
                    onClick = { sendManualRequest(context) },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Palette.Help,
                        contentColor = Color.White
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        stringResource(R.string.call_me),
                        modifier = Modifier.fillMaxWidth(),
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.titleMedium
                    )
                }
            }
            if (granted && BuildConfig.DEBUG) {
                item {
                    Button(
                        onClick = { MonitoringService.forceAnomaly(context, "high_pulse_at_rest") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 24.dp)
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

@Composable
private fun Line(text: String, color: Color = Color.Unspecified) {
    Text(text, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center, color = color)
}

private fun sendManualRequest(context: Context) {
    MonitoringService.sendEvent(
        context,
        EventMessage(
            id = UUID.randomUUID().toString(),
            type = "manual_request",
            measuredAt = Instant.now().toString()
        )
    )
}
