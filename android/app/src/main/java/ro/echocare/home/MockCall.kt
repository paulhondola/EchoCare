package ro.echocare.home

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import ro.echocare.MockAnswer
import ro.echocare.MockCall
import ro.echocare.R
import ro.echocare.ui.Banner
import ro.echocare.ui.Kind
import ro.echocare.ui.Rule
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

// The mock call card (design §6.2): the senior answers on the phone's screen what a call would ask.
// Campaign calls ask three questions (Q8); the welcome call asks for consent (Q11).

// Larger than SnButton's 44dp: these are the buttons a senior presses
private val BUTTON_HEIGHT = 56.dp

/** The days the server reads (design §4.2), in the order of [DAY_LABELS]. */
val DAYS = listOf("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")

private val DAY_LABELS = listOf(
    R.string.day_luni,
    R.string.day_marti,
    R.string.day_miercuri,
    R.string.day_joi,
    R.string.day_vineri,
    R.string.day_sambata,
    R.string.day_duminica
)

// What the buttons send: the server's values for each answer, "unknown" for „Nu știu”.
private val FEELINGS = listOf("ok" to R.string.feeling_ok, "unwell" to R.string.feeling_unwell)
private val DAY_CHOICES = DAYS.zip(DAY_LABELS) + ("unknown" to R.string.day_unknown)
private val SHELTERS = listOf("yes" to R.string.yes, "no" to R.string.no)

/** The body of „Trimite răspunsurile”: null until all three questions are answered (Q8). */
fun campaignAnswer(feeling: String?, day: String?, shelter: String?): MockAnswer? =
    if (feeling != null && day != null && shelter != null) {
        MockAnswer(feeling = feeling, day = day, shelter = shelter)
    } else {
        null
    }

/**
 * The card after a read that answered [status] (null: no answer at all). Only the server's own
 * answer changes it: 200 is [body], and 204 (nothing due), 403 and 404 (production) are no card.
 * A lost connection or a 5xx, say a redeploy, keeps [previous] so the senior's choices survive
 * (design §6.2).
 */
fun cardAfterRead(status: Int?, body: MockCall?, previous: MockCall?): MockCall? = when (status) {
    200 -> body
    204, 403, 404 -> null
    else -> previous
}

/**
 * Whether a post that answered [status] (null: no answer at all) is done with the card: the server
 * took it (2xx) or refused it (4xx, a 409 and a 422 included), so the page rereads. Otherwise the
 * answer may not have arrived, and the card stays for the senior to press again (design §6.2).
 */
fun answerSettled(status: Int?): Boolean = status != null && status in 200..499

/** The campaign's code and its kind as „Cod galben de caniculă”; null for a value this build lacks. */
@Composable
private fun warningLine(call: MockCall): String? {
    val level = when (call.level) {
        "yellow" -> R.string.level_yellow
        "red" -> R.string.level_red
        else -> return null
    }
    val kind = when (call.kind) {
        "cold" -> R.string.kind_cold
        "heat" -> R.string.kind_heat
        else -> return null
    }
    return stringResource(R.string.mock_warning, stringResource(level), stringResource(kind))
}

/** [onAnswer] gets the body to post: the three choices, `declined`, or the consent. */
@Composable
fun MockCallCard(call: MockCall, onAnswer: (MockAnswer) -> Unit) {
    val welcome = call.trigger == "welcome"
    val tone = when {
        welcome -> Tone.Link
        call.level == "red" -> Tone.Rosu
        else -> Tone.Galben
    }
    Column(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Banner(stringResource(R.string.mock_calling), tone)
        if (!welcome) {
            warningLine(call)?.let { Text(it, style = MaterialTheme.typography.titleMedium) }
        }
        Text(
            stringResource(R.string.mock_note),
            color = Palette.FgMuted,
            style = MaterialTheme.typography.bodyMedium
        )
        if (welcome) Welcome(call, onAnswer) else Campaign(call, onAnswer)
        Rule()
    }
}

@Composable
private fun Campaign(call: MockCall, onAnswer: (MockAnswer) -> Unit) {
    // A new call starts with nothing chosen
    var feeling by remember(call.callId) { mutableStateOf<String?>(null) }
    var day by remember(call.callId) { mutableStateOf<String?>(null) }
    var shelter by remember(call.callId) { mutableStateOf<String?>(null) }

    Question(R.string.q_feeling, FEELINGS, feeling) { feeling = it }
    Question(R.string.q_day, DAY_CHOICES, day) { day = it }
    val heat = call.kind == "heat"
    val shelterQuestion = if (heat) R.string.q_shelter_heat else R.string.q_shelter_cold
    Question(shelterQuestion, SHELTERS, shelter) { shelter = it }

    val answer = campaignAnswer(feeling, day, shelter)
    SnButton(
        stringResource(R.string.mock_send),
        { answer?.let(onAnswer) },
        Modifier.fillMaxWidth().heightIn(min = BUTTON_HEIGHT),
        kind = Kind.Success,
        enabled = answer != null
    )
    SnButton(
        stringResource(R.string.mock_later),
        { onAnswer(MockAnswer(declined = true)) },
        Modifier.fillMaxWidth().heightIn(min = BUTTON_HEIGHT),
        kind = Kind.Outline
    )
}

@Composable
private fun Welcome(call: MockCall, onAnswer: (MockAnswer) -> Unit) {
    Text(stringResource(R.string.welcome_title), style = MaterialTheme.typography.titleLarge)
    call.consentText?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
    // Equal buttons: neither answer is nudged
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        SnButton(
            stringResource(R.string.yes),
            { onAnswer(MockAnswer(consent = true)) },
            Modifier.heightIn(min = BUTTON_HEIGHT),
            kind = Kind.Outline
        )
        SnButton(
            stringResource(R.string.no),
            { onAnswer(MockAnswer(consent = false)) },
            Modifier.heightIn(min = BUTTON_HEIGHT),
            kind = Kind.Outline
        )
    }
}

/** One question over its answers, each a large button; the [chosen] value is filled in. */
@Composable
private fun Question(
    @StringRes text: Int,
    options: List<Pair<String, Int>>,
    chosen: String?,
    onChoose: (String) -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(text), style = MaterialTheme.typography.titleMedium)
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            options.forEach { (value, label) ->
                val picked = value == chosen
                SnButton(
                    stringResource(label),
                    { onChoose(value) },
                    Modifier
                        .heightIn(min = BUTTON_HEIGHT)
                        .semantics { selected = picked },
                    kind = if (picked) Kind.Success else Kind.Outline
                )
            }
        }
    }
}
