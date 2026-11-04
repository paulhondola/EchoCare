package ro.echocare.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import java.time.ZoneId
import ro.echocare.CallRow
import ro.echocare.R
import ro.echocare.SeniorPage
import ro.echocare.ui.Banner
import ro.echocare.ui.CallButton
import ro.echocare.ui.Chip
import ro.echocare.ui.FieldRow
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
    RereadWhileShown { vm.reread(id) }
    val title = (vm.page as? Load.Ready)?.value?.formOfAddress ?: stringResource(R.string.app_name)
    HomeScaffold(title, onBack = onBack, menu = menu) {
        LoadBody(vm.page, onRetry = { vm.reread(id) }, onSessionEnd = onSessionEnd) { senior ->
            // The senior's home only: the warning the campaign's calls are about (Q5)
            if (id == null && vm.warning) {
                Banner(stringResource(R.string.warning_active), Tone.Galben)
            }
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
                // „Editează” for the medic, in every state (04 §2, SE9)
                val edit = onEdit
                SeniorDetails(
                    senior,
                    callSenior = id != null,
                    action = edit?.let {
                        { SnButton(stringResource(R.string.edit), { it(senior.id) }) }
                    }
                )
                // A senior's page opened from a list: the caregiver's and the medic's (UC-12)
                vm.calls?.let { RecentCalls(recentCalls(it)) }
            }
        }
    }
}

/**
 * One senior, laid out like the dashboard's dossier: labelled rows, 1dp between rows, 2dp under a
 * group. The page and the form's step 4 show it. [callSenior] is false on the senior's own page,
 * since they do not need a button to call themselves; [calls] false hides every call button.
 */
@Composable
fun SeniorDetails(
    senior: SeniorPage,
    callSenior: Boolean,
    calls: Boolean = true,
    action: (@Composable () -> Unit)? = null
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
            action?.invoke()
        }
        Rule()

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

/** „Apeluri recente”: when, what started it, and the code it ended with or its state. */
@Composable
private fun RecentCalls(calls: List<CallRow>) {
    SectionLabel(
        stringResource(R.string.section_recent_calls),
        Modifier.padding(top = 20.dp, bottom = 4.dp)
    )
    if (calls.isEmpty()) {
        Text(
            stringResource(R.string.no_recent_calls),
            Modifier.padding(vertical = 12.dp),
            color = Palette.FgMuted
        )
    }
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
            Rule(strong = i == calls.lastIndex)
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
