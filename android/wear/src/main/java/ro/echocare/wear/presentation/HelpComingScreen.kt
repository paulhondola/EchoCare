package ro.echocare.wear.presentation

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.wear.compose.material3.CircularProgressIndicator
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.Text
import kotlinx.coroutines.delay
import ro.echocare.wear.R
import ro.echocare.wear.monitoring.Alert
import ro.echocare.wear.monitoring.HELP_SHOWN_MS
import ro.echocare.wear.monitoring.HelpPhase
import ro.echocare.wear.presentation.theme.Palette

/**
 * „Help is coming”, as the Apple Watch's `HelpComingView.swift` (design 2026-11-14, watch senior
 * UI): shown after „Nu mă simt bine”, „Nu” or a prompt's timeout. It says the team is being told,
 * „Încercăm din nou…” when the phone hasn't answered in 20 s, and ✓ only once the phone acks, which
 * it does after FastAPI has recorded the event (04 §3). The ✓ goes home after a minute; a tap goes
 * home once retrying or received.
 */
@Composable
fun HelpComingScreen(alert: Alert, dismiss: () -> Unit) {
    var nowMs by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(1_000)
            nowMs = System.currentTimeMillis()
        }
    }
    LaunchedEffect(alert.receivedAtMs) {
        if (alert.receivedAtMs == null) return@LaunchedEffect
        delay(HELP_SHOWN_MS)
        dismiss()
    }
    val phase = alert.phase(nowMs)
    Box(
        Modifier
            .fillMaxSize()
            // With no ack (phone off, no network) the senior must not be stuck here; the event
            // stays queued and is resent either way. Not while sending: see `Alert.canDismiss`
            .clickable { if (alert.canDismiss(System.currentTimeMillis())) dismiss() },
        contentAlignment = Alignment.Center
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            if (phase == HelpPhase.RECEIVED) {
                Box(
                    Modifier
                        .size(64.dp)
                        .background(Palette.Yes, CircleShape)
                        .clearAndSetSemantics {},
                    contentAlignment = Alignment.Center
                ) { Text("✓", color = Color.White, fontSize = 32.sp) }
                Centered(stringResource(R.string.help_received), headline = true)
                Centered(stringResource(R.string.help_answer_phone))
            } else {
                CircularProgressIndicator(Modifier.size(40.dp))
                Centered(stringResource(R.string.help_sending), headline = true)
                Centered(
                    stringResource(
                        if (phase == HelpPhase.RETRYING) {
                            R.string.help_retrying
                        } else {
                            R.string.help_keep_phone
                        }
                    ),
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun Centered(text: String, headline: Boolean = false, color: Color = Color.Unspecified) {
    Text(
        text,
        modifier = Modifier.fillMaxWidth(),
        textAlign = TextAlign.Center,
        color = color,
        style = if (headline) {
            MaterialTheme.typography.titleMedium
        } else {
            MaterialTheme.typography.bodyMedium
        }
    )
}
