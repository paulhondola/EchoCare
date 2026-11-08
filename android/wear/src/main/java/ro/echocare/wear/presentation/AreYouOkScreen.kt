package ro.echocare.wear.presentation

import android.content.Context
import android.util.Log
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
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.delay
import ro.echocare.shared.DataLayer
import ro.echocare.shared.EventMessage
import ro.echocare.shared.EventSnapshot
import ro.echocare.wear.R

// shortcut: 15 s for the demo; production should use 120_000 ms (UC-09 §2 step 3)
private const val PROMPT_TIMEOUT_MS = 15_000L

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
        sendFallEvent(context, fallId, measuredAt, type, snapshot, onDone)
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

private fun sendFallEvent(
    context: Context,
    fallId: String,
    measuredAt: String,
    type: String,
    snapshot: EventSnapshot,
    onDone: () -> Unit
) {
    Log.i("SentinelaMonitor", "sending $type event id=$fallId")
    val msg = EventMessage(id = fallId, type = type, measuredAt = measuredAt, snapshot = snapshot)
    Wearable.getNodeClient(context).connectedNodes
        .addOnSuccessListener { nodes ->
            if (nodes.isEmpty()) {
                Log.i("SentinelaMonitor", "$type event skipped: no connected nodes")
                onDone()
                return@addOnSuccessListener
            }
            nodes.forEach { node ->
                Wearable.getMessageClient(context)
                    .sendMessage(node.id, DataLayer.EVENT, msg.toBytes())
                    .addOnSuccessListener {
                        Log.i("SentinelaMonitor", "$type event sent to ${node.displayName}")
                    }
                    .addOnFailureListener {
                        Log.i(
                            "SentinelaMonitor",
                            "$type event failed to ${node.displayName}: ${it.message}"
                        )
                    }
            }
            onDone()
        }
        .addOnFailureListener {
            Log.i("SentinelaMonitor", "$type event node lookup failed: ${it.message}")
            onDone()
        }
}
