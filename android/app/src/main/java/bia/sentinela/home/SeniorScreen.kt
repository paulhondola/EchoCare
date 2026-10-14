package bia.sentinela.home

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
import bia.sentinela.R
import bia.sentinela.SeniorPage
import bia.sentinela.ui.CallButton
import bia.sentinela.ui.FieldRow
import bia.sentinela.ui.PhoneNumber
import bia.sentinela.ui.Rule
import bia.sentinela.ui.SectionLabel
import bia.sentinela.ui.formatPhone
import bia.sentinela.ui.theme.Mono
import bia.sentinela.ui.theme.Palette

/**
 * One senior's page: everything GET /seniors/{id} returns, the same for every role (seniors SE7).
 * [id] is null on the senior's own home, which has the menu and no back arrow.
 */
@Composable
fun SeniorScreen(
    id: String?,
    onBack: (() -> Unit)?,
    menu: @Composable () -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: SeniorViewModel = hiltViewModel()
) {
    RereadWhileShown { vm.reread(id) }
    val title = (vm.page as? Load.Ready)?.value?.formOfAddress ?: stringResource(R.string.app_name)
    HomeScaffold(title, onBack = onBack, menu = menu) {
        LoadBody(vm.page, onRetry = { vm.reread(id) }, onSessionEnd = onSessionEnd) { senior ->
            Page(senior, own = id == null)
        }
    }
}

/** Laid out like the dashboard's dossier: labelled rows, 1dp between rows, 2dp under a group. */
@Composable
private fun Page(senior: SeniorPage, own: Boolean) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 20.dp)
            .widthIn(max = 600.dp)
    ) {
        Column(
            Modifier.padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text(senior.fullName, style = MaterialTheme.typography.headlineSmall)
            StateLabel(senior.state)
        }
        Rule()

        // The senior does not need a button to call themselves
        FieldRow(
            stringResource(R.string.label_phone),
            action = if (own) null else ({ CallButton(senior.phone) })
        ) {
            PhoneNumber(senior.phone, senior.landline)
        }
        FieldRow(stringResource(R.string.label_address)) { Value(place(senior)) }
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
                    CallButton(c.phone)
                }
                Rule(strong = i == senior.caregivers.lastIndex)
            }
        }
    }
}

@Composable
private fun Value(text: String) {
    Text(text, style = MaterialTheme.typography.bodyLarge)
}

/** The street with block, staircase, floor and apartment (G13), from what was filled in. */
@Composable
private fun place(senior: SeniorPage): String = listOfNotNull(
    listOfNotNull(senior.street, senior.streetNumber).joinToString(" ").ifBlank { null },
    senior.block?.let { stringResource(R.string.address_block, it) },
    senior.staircase?.let { stringResource(R.string.address_staircase, it) },
    senior.floor?.let { stringResource(R.string.address_floor, it) },
    senior.apartment?.let { stringResource(R.string.address_apartment, it) }
).joinToString(", ").ifBlank { stringResource(R.string.no_address) }
