package ro.echocare.wear.presentation

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
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
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import kotlinx.coroutines.delay
import ro.echocare.shared.EventMessage
import ro.echocare.shared.EventSnapshot
import ro.echocare.wear.BuildConfig
import ro.echocare.wear.R
import ro.echocare.wear.monitoring.MonitoringService

// 06 §3: 15 s in the demo, 2 min in production (UC-09 §2 step 3)
private val PROMPT_TIMEOUT_MS: Long = if (BuildConfig.DEMO) 15_000L else 120_000L

/**
 * „Sunteți bine?" — shown when the fall detector or an anomaly rule fires (UC-09). The senior
 * has [PROMPT_TIMEOUT_MS] to say they are fine; silence or „Nu" sends the event and starts a call.
 */
@Composable
fun AreYouOkScreen(
    fallId: String,
    measuredAt: String,
    type: String,
    snapshot: EventSnapshot,
    onDone: () -> Unit
) {
    val context = LocalContext.current
    var done by remember { mutableStateOf(false) }
    var remainingMs by remember { mutableLongStateOf(PROMPT_TIMEOUT_MS) }

    fun sendEvent() {
        if (done) return
        done = true
        MonitoringService.sendEvent(
            context,
            EventMessage(id = fallId, type = type, measuredAt = measuredAt, snapshot = snapshot)
        )
        onDone()
    }

    LaunchedEffect(Unit) {
        while (remainingMs > 0 && !done) {
            delay(500)
            remainingMs = maxOf(0, remainingMs - 500)
        }
        sendEvent()
    }

    val listState = rememberTransformingLazyColumnState()
    ScreenScaffold(scrollState = listState) { contentPadding ->
        TransformingLazyColumn(contentPadding = contentPadding, state = listState) {
            item {
                ListHeader { Text(stringResource(R.string.are_you_ok_title)) }
            }
            item {
                Text(
                    stringResource(R.string.are_you_ok_countdown, remainingMs / 1_000),
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.titleLarge
                )
            }
            item {
                Button(
                    onClick = {
                        if (!done) {
                            done = true
                            onDone()
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(stringResource(R.string.are_you_ok_yes))
                }
            }
            item {
                Button(
                    onClick = { sendEvent() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(stringResource(R.string.are_you_ok_no))
                }
            }
        }
    }
}
