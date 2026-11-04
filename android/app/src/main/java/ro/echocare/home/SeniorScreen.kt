package ro.echocare.home

import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import java.time.ZoneId
import ro.echocare.CallRow
import ro.echocare.IncidentCall
import ro.echocare.R
import ro.echocare.SeniorPage
import ro.echocare.das.Transcript
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
 * One senior's page: everything GET /seniors/{id} returns, the same for every role (seniors SE7).
 * [id] is null on the senior's own home, which has the menu and no back arrow. [onEdit] opens the
 * medic's form.
 */
@Composable
fun SeniorScreen(
    id: String?,
    onBack: (() -> Unit)?,
    menu: @Composable () -> Unit,
    onSessionEnd: (Failure) -> Unit,
    onEdit: ((String) -> Unit)? = null,
    vm: SeniorViewModel = hiltViewModel()
) {
    val title = (vm.page as? Load.Ready)?.value?.formOfAddress ?: stringResource(R.string.app_name)
    HomeScaffold(title, onBack = onBack, menu = menu) {
        PatientPane(id, onSessionEnd, onEdit, vm = vm)
    }
}

/**
 * One senior's page without its scaffold: the body the page and Monitorizare's right pane share,
 * so a change to it is made once (UC-12). [id] null is the senior's own page. [onEdit] is given
 * to the medic only: with it the page adds her patient's stages, consent, every call with its
 * transcript, and the actions of her panel (UC-04, UC-12). [onChanged] runs after a command the
 * server answered, so Monitorizare's list beside the pane moves the patient at once.
 */
@Composable
fun PatientPane(
    id: String?,
    onSessionEnd: (Failure) -> Unit,
    onEdit: ((String) -> Unit)? = null,
    onChanged: () -> Unit = {},
    vm: SeniorViewModel = hiltViewModel(key = id)
) {
    RereadWhileShown { vm.reread(id) }
    // „Retragere consimțământ” asks first; „Semnătură” opens the consent text under the actions
    var withdrawing by rememberSaveable { mutableStateOf(false) }
    var signing by rememberSaveable { mutableStateOf(false) }
    LoadBody(vm.page, onRetry = { vm.reread(id) }, onSessionEnd = onSessionEnd) { senior ->
        // The senior's home only: the warning the campaign's calls are about (Q5)
        if (id == null && vm.warning) {
            Banner(stringResource(R.string.warning_active), Tone.Galben)
        }
        val medic = if (id != null) onEdit else null
        if (medic != null) CommandBanners(vm.notice, vm.numberChanged)
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 20.dp)
                .widthIn(max = 600.dp)
        ) {
            // The senior's home only: asks for a wellbeing call (UC-10)
            if (id == null) CallMeButton(vm.callMe, vm::requestCall)
            // The senior's home only: a call to answer here instead of on the phone (design §6.2)
            vm.mock?.let { MockCallCard(it, vm::answer) }
            SeniorDetails(
                senior,
                callSenior = id != null,
                below = medic?.let { edit ->
                    {
                        Stages(stagesOf(senior))
                        ConsentLine(senior)
                        Actions(
                            actionsFor(senior),
                            busy = vm.busy,
                            onAction = { action ->
                                when (action) {
                                    Action.CallAgain -> vm.callAgain(senior.id, onChanged)
                                    Action.Withdraw -> withdrawing = true
                                    Action.Sign -> signing = !signing
                                    Action.Edit -> {
                                        vm.editing()
                                        edit(senior.id)
                                    }
                                }
                            }
                        )
                        if (signing && Action.Sign in actionsFor(senior)) Signing()
                    }
                }
            )
            // A senior's page opened from a list: the caregiver's and the medic's (UC-12). The
            // medic sees every call and what was said; a caregiver a short list (01 §6)
            vm.calls?.let { calls ->
                if (medic != null) {
                    CallList(
                        R.string.section_calls,
                        calls,
                        Transcripts(vm.transcripts, vm::openTranscript)
                    )
                } else {
                    CallList(R.string.section_recent_calls, recentCalls(calls))
                }
            }
        }
        if (withdrawing) {
            WithdrawDialog(
                senior.formOfAddress,
                busy = vm.busy,
                onConfirm = {
                    withdrawing = false
                    vm.withdraw(senior.id, onChanged)
                },
                onDismiss = { withdrawing = false }
            )
        }
    }
}

/** The banners after a command and after a new number (UC-12, 04 §2). */
@Composable
private fun CommandBanners(notice: CommandOutcome?, numberChanged: Boolean) {
    when (notice) {
        is CommandOutcome.Refused -> Banner(
            stringResource(
                if (notice.reason == null) R.string.not_allowed_action else R.string.changed_state
            ),
            Tone.Galben
        )

        CommandOutcome.Offline -> Banner(stringResource(R.string.offline_retry), Tone.Galben)

        CommandOutcome.Done, null -> {}
    }
    if (numberChanged) Banner(stringResource(R.string.number_changed), Tone.Link)
}

/** The enrollment's stages under the name: lit up to where the senior is (03 §7, UC-04). */
@Composable
private fun Stages(stages: List<Stage>) {
    val zone = ZoneId.systemDefault()
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        stages.forEach { stage ->
            Column(
                Modifier
                    .weight(1f)
                    .drawBehind {
                        drawRect(
                            if (stage.reached) Palette.Verde else Palette.Line,
                            size = Size(size.width, 3.dp.toPx())
                        )
                    }
                    .padding(top = 9.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp)
            ) {
                Text(
                    stringResource(stage.label),
                    color = if (stage.reached) Palette.Fg else Palette.FgSubtle,
                    style = MaterialTheme.typography.labelMedium
                )
                stage.at?.let {
                    Text(
                        shortDate(it, zone),
                        color = if (stage.reached) Palette.FgMuted else Palette.FgSubtle,
                        style = MaterialTheme.typography.labelSmall
                    )
                }
            }
        }
    }
}

/** „Dat · la apel · 4 nov. 2026” and „Semnat pe tabletă · …”; neither, no line (04 §1, G7). */
@Composable
private fun ConsentLine(senior: SeniorPage) {
    val zone = ZoneId.systemDefault()
    val lines = listOfNotNull(
        senior.consent?.let {
            stringResource(
                R.string.consent_line,
                CONSENT_DECISIONS[it.decision]?.let { label -> stringResource(label) }
                    ?: it.decision,
                CONSENT_METHODS[it.method]?.let { label -> stringResource(label) } ?: it.method,
                shortDate(it.at, zone, year = true)
            )
        },
        senior.signedAt?.let {
            stringResource(R.string.signed_on_tablet, shortDate(it, zone, year = true))
        }
    )
    if (lines.isEmpty()) return
    Row(
        Modifier
            .fillMaxWidth()
            .padding(top = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        SectionLabel(stringResource(R.string.consent_label), Modifier.width(112.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            lines.forEach { Text(it, style = MaterialTheme.typography.bodyMedium) }
        }
    }
}

/** The actions of the senior's state, all in sight (UC-12, design "The patient"). */
@Composable
private fun Actions(actions: List<Action>, busy: Boolean, onAction: (Action) -> Unit) {
    if (actions.isEmpty()) return
    FlowRow(
        Modifier
            .fillMaxWidth()
            .padding(top = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        actions.forEach { action ->
            when (action) {
                // At once, no confirmation (UC-04)
                Action.CallAgain -> SnButton(
                    stringResource(R.string.call_again),
                    { onAction(action) },
                    kind = Kind.Success,
                    enabled = !busy
                )

                Action.Withdraw -> SnButton(
                    stringResource(R.string.withdraw),
                    { onAction(action) },
                    kind = Kind.Danger,
                    enabled = !busy
                )

                Action.Sign -> SnButton(stringResource(R.string.sign), { onAction(action) })

                Action.Edit -> SnButton(stringResource(R.string.edit_data), { onAction(action) })
            }
        }
    }
}

/**
 * The consent text and the signature, opened by „Semnătură” under the actions (G7, UC-01 step 5).
 * The signature step of #54 fills it.
 */
@Composable
private fun Signing() {
    // The pad and its consent text arrive with the signature step; nothing shows until then
}

/** „Retrageți consimțământul pentru …?”: the withdrawal cannot be undone (04 §2). */
@Composable
private fun WithdrawDialog(
    formOfAddress: String,
    busy: Boolean,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        shape = RectangleShape,
        containerColor = Palette.Subtle,
        title = {
            Text(
                stringResource(R.string.withdraw_title, formOfAddress),
                style = MaterialTheme.typography.titleMedium
            )
        },
        text = {
            Text(
                stringResource(R.string.withdraw_text),
                color = Palette.FgSoft,
                style = MaterialTheme.typography.bodyMedium
            )
        },
        confirmButton = {
            SnButton(
                stringResource(R.string.withdraw_confirm),
                onConfirm,
                kind = Kind.Danger,
                enabled = !busy
            )
        },
        dismissButton = { SnButton(stringResource(R.string.cancel), onDismiss) }
    )
}

/**
 * One senior, laid out like the dashboard's dossier: labelled rows, 1dp between rows, 2dp under a
 * group. The page and the form's step 4 show it. [callSenior] is false on the senior's own page,
 * since they do not need a button to call themselves; [calls] false hides every call button.
 * [below] goes under the name, over the rule: the medic's stages, consent and actions.
 */
@Composable
fun SeniorDetails(
    senior: SeniorPage,
    callSenior: Boolean,
    calls: Boolean = true,
    below: (@Composable () -> Unit)? = null
) {
    Column {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.Bottom
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(senior.fullName, style = MaterialTheme.typography.headlineSmall)
                StateLabel(senior.state)
                CodeLabel(senior.code, senior.reason)
                if (showsCallBadge(senior)) Chip(stringResource(R.string.call_live), Tone.Galben)
                watchChip(senior.watchState)?.let { (label, tone) ->
                    Chip(stringResource(label), tone)
                }
            }
        }
        below?.invoke()
        Rule(Modifier.padding(top = if (below != null) 16.dp else 0.dp))

        FieldRow(
            stringResource(R.string.label_phone),
            action = if (calls && callSenior) ({ CallButton(senior.phone) }) else null
        ) {
            PhoneNumber(senior.phone, senior.landline)
        }
        FieldRow(stringResource(R.string.label_address)) {
            Value(
                place(
                    senior.street,
                    senior.streetNumber,
                    senior.block,
                    senior.staircase,
                    senior.floor,
                    senior.apartment
                )
            )
        }
        senior.intercomCode?.let {
            FieldRow(stringResource(R.string.label_intercom)) { Text(it, style = Mono) }
        }
        senior.keyHolder?.let { FieldRow(stringResource(R.string.label_key_holder)) { Value(it) } }
        senior.landmark?.let { FieldRow(stringResource(R.string.label_landmark)) { Value(it) } }
        senior.callWindow?.let {
            FieldRow(stringResource(R.string.section_call_window)) { Value(it) }
        }
        FieldRow(stringResource(R.string.role_medic), last = true) {
            Value(
                listOfNotNull(senior.medic.displayName, senior.medic.practice).joinToString(" · ")
            )
        }

        SectionLabel(
            stringResource(R.string.section_caregivers),
            Modifier.padding(top = 20.dp, bottom = 4.dp)
        )
        if (senior.caregivers.isEmpty()) {
            Text(
                stringResource(R.string.no_caregivers),
                Modifier.padding(vertical = 12.dp),
                color = Palette.FgMuted
            )
        }
        senior.caregivers.forEachIndexed { i, c ->
            Column {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(vertical = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            listOfNotNull(c.displayName, c.relation).joinToString(" · "),
                            style = MaterialTheme.typography.titleMedium
                        )
                        Text(formatPhone(c.phone), style = Mono, color = Palette.FgSoft)
                    }
                    if (calls) CallButton(c.phone)
                }
                Rule(strong = i == senior.caregivers.lastIndex)
            }
        }
    }
}

/** The medic's „Transcriere” on each call: what was read, and how to read one (04 §1). */
private class Transcripts(val read: Map<String, Load<IncidentCall>>, val open: (String) -> Unit)

/**
 * „Apeluri recente” or, for the medic, „Apeluri”: when, what started it, and the code it ended
 * with or its state. With [transcripts], each row opens what was said under it.
 */
@Composable
private fun CallList(
    @StringRes title: Int,
    calls: List<CallRow>,
    transcripts: Transcripts? = null
) {
    SectionLabel(stringResource(title), Modifier.padding(top = 20.dp, bottom = 4.dp))
    if (calls.isEmpty()) {
        Text(
            stringResource(R.string.no_recent_calls),
            Modifier.padding(vertical = 12.dp),
            color = Palette.FgMuted
        )
    }
    // The rows the medic unfolded; „Ascunde” folds one, and the transcript stays read
    var shown by remember { mutableStateOf(emptySet<String>()) }
    val zone = ZoneId.systemDefault()
    calls.forEachIndexed { i, call ->
        Column {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        stringResource(
                            R.string.recent_call_line,
                            callTime(call, zone),
                            TRIGGER_LABELS[call.trigger]?.let { stringResource(it) }
                                ?: call.trigger
                        ),
                        style = MaterialTheme.typography.titleMedium
                    )
                    call.reason?.let {
                        Text(
                            it,
                            color = Palette.FgMuted,
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
                when (val result = outcome(call)) {
                    is Outcome.Code -> Chip(
                        stringResource(CODE_LABELS.getValue(result.code)),
                        CODE_TONES.getValue(result.code)
                    )

                    is Outcome.State -> Chip(
                        CALL_STATE_LABELS[result.state]?.let { stringResource(it) } ?: result.state,
                        stateTone(result.state)
                    )
                }
            }
            transcripts?.let {
                val open = call.id in shown
                SnButton(
                    stringResource(if (open) R.string.hide else R.string.transcript),
                    {
                        shown = if (open) shown - call.id else shown + call.id
                        if (!open) it.open(call.id)
                    },
                    Modifier.padding(bottom = 12.dp),
                    kind = Kind.Link
                )
                if (open) it.read[call.id]?.let { read -> TranscriptOf(read) }
            }
            Rule(strong = i == calls.lastIndex)
        }
    }
}

/** One call's transcript under its row, as on the DAS incident page (UC-12). */
@Composable
private fun TranscriptOf(read: Load<IncidentCall>) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 12.dp)
            .background(Palette.Subtle)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        when (read) {
            Load.Loading -> CircularProgressIndicator(Modifier.size(20.dp), color = Palette.FgMuted)

            is Load.Ready -> if (read.value.turns.isEmpty() && read.value.reports.isEmpty()) {
                Text(stringResource(R.string.no_transcript), color = Palette.FgMuted)
            } else {
                Transcript(read.value)
            }

            // „Transcriere” again reads it again
            is Load.Failed -> Text(
                stringResource(
                    when (read.failure) {
                        Failure.NotFound -> R.string.not_found
                        Failure.NotAllowed -> R.string.not_allowed
                        else -> R.string.no_connection
                    }
                ),
                color = Palette.FgMuted
            )
        }
    }
}

@Composable
private fun Value(text: String) {
    Text(text, style = MaterialTheme.typography.bodyLarge)
}

/**
 * The street with block, staircase, floor and apartment (G13), from what was filled in. The
 * senior's page and the DAS incident page both show it.
 */
@Composable
fun place(
    street: String?,
    streetNumber: String?,
    block: String?,
    staircase: String?,
    floor: String?,
    apartment: String?
): String = listOfNotNull(
    listOfNotNull(street, streetNumber).joinToString(" ").ifBlank { null },
    block?.let { stringResource(R.string.address_block, it) },
    staircase?.let { stringResource(R.string.address_staircase, it) },
    floor?.let { stringResource(R.string.address_floor, it) },
    apartment?.let { stringResource(R.string.address_apartment, it) }
).joinToString(", ").ifBlank { stringResource(R.string.no_address) }
