package ro.echocare.wear.presentation

import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.VibratorManager
import android.speech.tts.TextToSpeech
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.CircularProgressIndicator
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ProgressIndicatorDefaults
import androidx.wear.compose.material3.Text
import java.util.Locale
import kotlinx.coroutines.delay
import ro.echocare.shared.EventMessage
import ro.echocare.shared.EventSnapshot
import ro.echocare.wear.BuildConfig
import ro.echocare.wear.R
import ro.echocare.wear.monitoring.MonitoringService
import ro.echocare.wear.presentation.theme.Palette

// 06 §3: 15 s in the demo, 2 min in production (UC-09 §2 step 3)
private val PROMPT_TIMEOUT_MS: Long = if (BuildConfig.DEMO) 15_000L else 120_000L
private const val BUZZ_EVERY_MS = 3_000L
private const val FALL_BEEP_MS = 1_000L

private fun beep() {
    val tone = ToneGenerator(AudioManager.STREAM_ALARM, ToneGenerator.MAX_VOLUME)
    tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 600)
    // Released after the tone ends; releasing at once cuts it off
    Handler(Looper.getMainLooper()).postDelayed({ tone.release() }, 800)
}

/**
 * „Sunteți bine?”, shown when the fall detector or an anomaly rule fires (UC-09), redesigned for
 * seniors like the Apple Watch's `AreYouOkView.swift` (design 2026-11-14, watch senior UI). The
 * senior has [PROMPT_TIMEOUT_MS] to say they are fine; „Nu” or silence sends the event and starts a
 * call. Two big buttons fill the screen, an amber ring around the edge drains as the time runs out,
 * and the watch asks the question aloud when it has a Romanian voice.
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
    val question = stringResource(R.string.are_you_ok_title)

    fun sendEvent() {
        if (done) return
        done = true
        MonitoringService.sendEvent(
            context,
            EventMessage(id = fallId, type = type, measuredAt = measuredAt, snapshot = snapshot)
        )
        onDone()
    }

    // The service buzzed once when it raised the prompt. A watch on a lowered wrist is easy to
    // miss, so it buzzes again every 3 s, and a fall also beeps once after 1 s (as `Monitor.swift`)
    LaunchedEffect(Unit) {
        val vibrator = context.getSystemService(VibratorManager::class.java).defaultVibrator
        var elapsedMs = 0L
        while (remainingMs > 0 && !done) {
            delay(500)
            elapsedMs += 500
            remainingMs = maxOf(0, remainingMs - 500)
            if (type == "fall" && elapsedMs == FALL_BEEP_MS) beep()
            if (elapsedMs % BUZZ_EVERY_MS == 0L && !done) {
                vibrator.vibrate(
                    VibrationEffect.createOneShot(400, VibrationEffect.DEFAULT_AMPLITUDE)
                )
            }
        }
        sendEvent()
    }

    // Says „Sunteți bine?” once, only with a Romanian voice: a wrong-language voice would confuse
    // more than help
    DisposableEffect(Unit) {
        var tts: TextToSpeech? = null
        tts = TextToSpeech(context) { status ->
            val engine = tts ?: return@TextToSpeech
            if (status == TextToSpeech.SUCCESS &&
                engine.setLanguage(Locale.forLanguageTag("ro-RO")) >= TextToSpeech.LANG_AVAILABLE
            ) {
                engine.speak(question, TextToSpeech.QUEUE_FLUSH, null, fallId)
            }
        }
        onDispose { tts?.shutdown() }
    }

    Box(Modifier.fillMaxSize()) {
        CircularProgressIndicator(
            progress = { remainingMs.toFloat() / PROMPT_TIMEOUT_MS },
            modifier = Modifier
                .fillMaxSize()
                .clearAndSetSemantics {},
            colors = ProgressIndicatorDefaults.colors(
                indicatorColor = Palette.Ring,
                trackColor = Color.Transparent
            )
        )
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 26.dp, vertical = 22.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                question,
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Black
            )
            Choice("✓  " + stringResource(R.string.are_you_ok_yes), Palette.Yes) {
                if (!done) {
                    done = true
                    onDone()
                }
            }
            Choice("✕  " + stringResource(R.string.are_you_ok_no), Palette.Help) { sendEvent() }
        }
    }
}

@Composable
private fun ColumnScope.Choice(label: String, fill: Color, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        colors = ButtonDefaults.buttonColors(containerColor = fill, contentColor = Color.White),
        modifier = Modifier
            .fillMaxWidth()
            .weight(1f)
    ) {
        Text(
            label,
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.titleMedium
        )
    }
}
