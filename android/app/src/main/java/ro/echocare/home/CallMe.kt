package ro.echocare.home

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.util.UUID
import ro.echocare.EventForm
import ro.echocare.EventResult
import ro.echocare.R
import ro.echocare.ui.Banner
import ro.echocare.ui.Kind
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone

// „Sunați-mă” on the senior's home (UC-10): asks FastAPI for a wellbeing call. The server queues it
// and the dialer rings the phone on its next tick; a tap while one is queued joins that call (04 §3).

/** What the button shows. */
enum class CallMe { Idle, Sending, Coming, NotSent }

/** A fresh id per tap, so only a resend of this very tap is a duplicate (04 §3). */
fun manualRequest(id: String = UUID.randomUUID().toString(), now: Instant = Instant.now()) =
    EventForm(id, "manual_request", now.toString())

/**
 * The state once the post answered. A 200 without a call means the server kept the event and
 * queued none, so nothing is coming; that, a refusal and a lost connection all invite another tap.
 */
fun callMeAfter(answer: Answer<EventResult>): CallMe =
    if (answer is Answer.Ok && answer.value.callId != null) CallMe.Coming else CallMe.NotSent

@Composable
fun CallMeButton(state: CallMe, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(bottom = 16.dp)) {
        when (state) {
            CallMe.Coming -> Banner(stringResource(R.string.call_me_sent), Tone.Verde)
            CallMe.NotSent -> Banner(stringResource(R.string.call_me_failed), Tone.Rosu)
            else -> {}
        }
        SnButton(
            stringResource(R.string.call_me),
            onClick,
            Modifier.fillMaxWidth().heightIn(min = BUTTON_HEIGHT),
            kind = Kind.Success,
            enabled = state != CallMe.Sending
        )
    }
}
