package ro.echocare.das

import android.content.ActivityNotFoundException
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import ro.echocare.IncidentCall
import ro.echocare.IncidentPage
import ro.echocare.R
import ro.echocare.home.CALL_STATE_LABELS
import ro.echocare.home.CODE_LABELS
import ro.echocare.home.CODE_TONES
import ro.echocare.home.EVENT_LABELS
import ro.echocare.home.Failure
import ro.echocare.home.HomeScaffold
import ro.echocare.home.Load
import ro.echocare.home.LoadBody
import ro.echocare.home.RereadWhileShown
import ro.echocare.home.TRIGGER_LABELS
import ro.echocare.home.place
import ro.echocare.ui.Banner
import ro.echocare.ui.CallButton
import ro.echocare.ui.Chip
import ro.echocare.ui.FieldRow
import ro.echocare.ui.Kind
import ro.echocare.ui.PhoneNumber
import ro.echocare.ui.Rule
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone
import ro.echocare.ui.formatPhone
import ro.echocare.ui.theme.Mono
import ro.echocare.ui.theme.Palette

/**
 * One incident on the DAS phone (UC-11, UC-12): what happened, how to get in, who to call, what
 * was said. One scrolling page; the action that the status allows stays pinned under it.
 */
@Composable
fun IncidentScreen(
    onBack: () -> Unit,
    onResolve: (String) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: IncidentViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    val ended = (vm.notice as? Notice.Ends)?.failure
    LaunchedEffect(ended) { ended?.let(onSessionEnd) }
    val title = (vm.page as? Load.Ready)?.value?.senior?.fullName.orEmpty()
    HomeScaffold(title, onBack = onBack, menu = {}) {
        LoadBody(vm.page, onRetry = vm::reread, onSessionEnd = onSessionEnd) { incident ->
            Column(Modifier.fillMaxSize()) {
                Column(
                    Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = 16.dp, vertical = 20.dp)
                        .widthIn(max = 600.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Summary(incident, vm.now)
                    Access(incident)
                    Phones(incident)
                    incident.event?.let { Event(it) }
                    Calls(incident.calls)
                }
                vm.notice?.let { NoticeBanner(it) }
                when (actFor(incident.status)) {
                    Act.Take -> ActionBar {
                        SnButton(
                            stringResource(R.string.take),
                            vm::take,
                            Modifier.fillMaxWidth(),
                            kind = Kind.Danger,
                            enabled = !vm.taking
                        )
                    }
                    Act.Resolve -> ActionBar {
                        SnButton(
                            stringResource(R.string.resolve),
                            { onResolve(vm.id) },
                            Modifier.fillMaxWidth(),
                            // The next step, as the dashboard's card; green is for Trimite
                            kind = Kind.Link
                        )
                    }
                    // Resolved meanwhile, or a status this build does not know
                    null -> {}
                }
            }
        }
    }
}

/** The pinned bar under the page: the one action the status allows (design §"The incident page"). */
@Composable
fun ActionBar(content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().background(Palette.Subtle)) {
        Rule()
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) { content() }
    }
}

/** A refused command, in the dashboard's words. [Notice.Ends] shows nothing: sign-in follows. */
@Composable
fun NoticeBanner(notice: Notice) {
    when (notice) {
        is Notice.TakenBy -> Banner(
            stringResource(R.string.taken_by_other, notice.name),
            Tone.Galben
        )
        is Notice.Says -> Banner(stringResource(notice.text), Tone.Galben)
        is Notice.Ends -> {}
    }
}

private val clock = DateTimeFormatter.ofPattern("HH:mm:ss")

// With the date, as the dashboard's `time`: an incident can stay open past midnight
private val dated = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")

/** [iso] in the phone's time zone; the API sends UTC. */
private fun local(iso: String, format: DateTimeFormatter): String =
    format.format(Instant.parse(iso).atZone(ZoneId.systemDefault()))

/** The status, the reason and the senior's own words. */
@Composable
private fun Summary(incident: IncidentPage, now: Instant) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
            itemVerticalAlignment = Alignment.CenterVertically
        ) {
            StatusChip(incident.status, incident.takenByName)
            if (incident.status == OPEN) {
                Text(
                    agoText(ago(incident.openedAt, now)),
                    color = Palette.FgMuted,
                    style = MaterialTheme.typography.bodySmall
                )
            }
            if (callLive(incident.calls)) Chip(stringResource(R.string.call_live), Tone.Galben)
        }
        Text(incident.reason, style = MaterialTheme.typography.titleLarge)
        seniorsWords(incident.calls)?.let { words ->
            Text(
                "„$words”",
                Modifier
                    .fillMaxWidth()
                    .background(Palette.Card)
                    .drawBehind { drawRect(Tone.Rosu.dot, size = Size(3.dp.toPx(), size.height)) }
                    .padding(start = 15.dp, end = 12.dp, top = 10.dp, bottom = 10.dp),
                style = MaterialTheme.typography.bodyLarge
            )
        }
    }
}

/** The address with what it takes to get in (G13), and Maps. */
@Composable
private fun Access(incident: IncidentPage) {
    val s = incident.senior
    val context = LocalContext.current
    SectionLabel(stringResource(R.string.section_access), Modifier.padding(top = 20.dp))
    Column {
        // The section's last row takes the 2dp rule, whichever details are filled in
        val tail = s.keyHolder == null && s.landmark == null
        FieldRow(stringResource(R.string.label_address), last = tail && s.intercomCode == null) {
            Text(
                place(s.street, s.streetNumber, s.block, s.staircase, s.floor, s.apartment),
                style = MaterialTheme.typography.bodyLarge
            )
        }
        s.intercomCode?.let {
            FieldRow(stringResource(R.string.label_intercom), last = tail) {
                Text(it, style = Mono)
            }
        }
        s.keyHolder?.let {
            FieldRow(stringResource(R.string.label_key_holder), last = s.landmark == null) {
                Value(it)
            }
        }
        s.landmark?.let {
            FieldRow(stringResource(R.string.label_landmark), last = true) { Value(it) }
        }
    }
    mapsUri(s, incident.event)?.let { uri ->
        SnButton(
            stringResource(R.string.open_in_maps),
            onClick = {
                try {
                    context.startActivity(Intent(Intent.ACTION_VIEW, uri.toUri()))
                } catch (e: ActivityNotFoundException) {
                    // No maps app: the address stays on screen
                }
            },
            Modifier.fillMaxWidth(),
            kind = Kind.Link
        )
    }
}

/** The senior first, then each caregiver, each with *Apelează* (UC-11 step 3). */
@Composable
private fun Phones(incident: IncidentPage) {
    SectionLabel(stringResource(R.string.label_phone), Modifier.padding(top = 20.dp))
    Column {
        PersonRow(
            name = { Text(incident.senior.fullName, style = MaterialTheme.typography.titleMedium) },
            number = {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) { PhoneNumber(incident.senior.phone, incident.senior.landline) }
            },
            e164 = incident.senior.phone,
            last = incident.caregivers.isEmpty()
        )
        incident.caregivers.forEachIndexed { i, c ->
            PersonRow(
                name = {
                    Text(
                        listOfNotNull(c.displayName, c.relation).joinToString(" · "),
                        style = MaterialTheme.typography.titleMedium
                    )
                },
                number = { Text(formatPhone(c.phone), style = Mono, color = Palette.FgSoft) },
                e164 = c.phone,
                last = i == incident.caregivers.lastIndex
            )
        }
    }
}

@Composable
private fun PersonRow(
    name: @Composable () -> Unit,
    number: @Composable () -> Unit,
    e164: String,
    last: Boolean
) {
    Column {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                name()
                number()
            }
            CallButton(e164)
        }
        Rule(strong = last)
    }
}

/** What set the incident off, and where (G16). */
@Composable
private fun Event(event: ro.echocare.TriggerEvent) {
    SectionLabel(stringResource(R.string.section_event), Modifier.padding(top = 20.dp))
    Column {
        FieldRow(stringResource(R.string.event_type)) {
            Value(EVENT_LABELS[event.type]?.let { stringResource(it) } ?: event.type)
        }
        val place = location(event)
        FieldRow(stringResource(R.string.event_measured_at), last = place == null) {
            Text(local(event.measuredAt, dated), style = Mono)
        }
        place?.let {
            FieldRow(stringResource(R.string.event_location), last = true) {
                Text(
                    it.accuracy?.let { m ->
                        stringResource(R.string.event_location_value, it.latitude, it.longitude, m)
                    } ?: stringResource(R.string.event_location_only, it.latitude, it.longitude),
                    style = Mono
                )
            }
        }
    }
}

/** Every call of the incident, newest first and open; older ones open on a tap. */
@Composable
private fun Calls(calls: List<IncidentCall>) {
    SectionLabel(stringResource(R.string.section_calls), Modifier.padding(top = 20.dp))
    if (calls.isEmpty()) {
        Text(stringResource(R.string.no_calls), color = Palette.FgMuted)
        return
    }
    val newest = newestFirst(calls)
    // Only the dispatcher's own taps are kept; the default follows the newest call
    val toggled = remember { mutableStateMapOf<String, Boolean>() }
    newest.forEach { call ->
        val expanded = expanded(call.id, newest.first().id, toggled)
        Column(
            Modifier
                .fillMaxWidth()
                .background(Palette.Subtle)
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(
                callLine(call),
                Modifier
                    .fillMaxWidth()
                    .clickable(role = Role.Button) { toggled[call.id] = !expanded },
                color = Palette.FgSoft,
                style = MaterialTheme.typography.labelLarge
            )
            if (expanded) Transcript(call)
        }
    }
}

/** "Ceas · încercarea 1 · Cod roșu"; a call with no final code shows its state. */
@Composable
private fun callLine(call: IncidentCall): String = stringResource(
    R.string.call_line,
    TRIGGER_LABELS[call.trigger]?.let { stringResource(it) } ?: call.trigger,
    call.attempt,
    CODE_LABELS[call.finalSeverity]?.let { stringResource(it) }
        ?: CALL_STATE_LABELS[call.state]?.let { stringResource(it) }
        ?: call.state
)

/** A call's turns and reported codes in time order; the medic's patient page shows it too (UC-12). */
@Composable
internal fun Transcript(call: IncidentCall) {
    timeline(call).forEach { line ->
        when (line) {
            is Line.Said -> Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val (who, color) = when (line.turn.speaker) {
                        "senior" -> R.string.speaker_senior to Palette.FgMuted
                        "agent" -> R.string.speaker_agent to Palette.Link
                        "das" -> R.string.speaker_das to Palette.Fg
                        else -> R.string.speaker_system to Palette.FgMuted
                    }
                    Text(
                        stringResource(who).uppercase(),
                        color = color,
                        style = MaterialTheme.typography.labelSmall
                    )
                    Text(local(line.at, clock), color = Palette.FgMuted, style = Mono)
                }
                Text(
                    if (line.turn.kind == "keys") {
                        stringResource(R.string.turn_keys, line.turn.content)
                    } else {
                        line.turn.content
                    },
                    style = MaterialTheme.typography.bodyMedium
                )
            }

            is Line.Flagged -> {
                val tone = CODE_TONES[line.report.severity] ?: Tone.Muted
                Text(
                    stringResource(
                        R.string.flagged,
                        CODE_LABELS[line.report.severity]?.let { stringResource(it) }
                            ?: line.report.severity,
                        line.report.reason
                    ),
                    Modifier
                        .fillMaxWidth()
                        .background(tone.fill)
                        .padding(horizontal = 8.dp, vertical = 6.dp),
                    color = tone.text,
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
    call.handoverAnswered?.let { answered ->
        Text(
            stringResource(if (answered) R.string.handover_call_yes else R.string.handover_call_no),
            color = if (answered) Palette.VerdeFg else Palette.RosuFg,
            style = MaterialTheme.typography.labelLarge
        )
    }
}

@Composable
private fun Value(text: String) {
    Text(text, style = MaterialTheme.typography.bodyLarge)
}
