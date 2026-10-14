package bia.sentinela.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
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
            Page(senior)
        }
    }
}

@Composable
private fun Page(senior: SeniorPage) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .widthIn(max = 600.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(senior.fullName, style = MaterialTheme.typography.titleLarge)
                StateLabel(senior.state)
            }
            Text(
                if (senior.landline) {
                    stringResource(R.string.landline_number, senior.phone)
                } else {
                    senior.phone
                }
            )
        }
        Section(R.string.section_address, addressLines(senior))
        senior.callWindow?.let { Section(R.string.section_call_window, listOf(it)) }
        Section(
            R.string.role_medic,
            listOf(
                listOfNotNull(senior.medic.displayName, senior.medic.practice).joinToString(" · ")
            )
        )
        Section(
            R.string.section_caregivers,
            senior.caregivers.map {
                listOfNotNull(it.displayName, it.relation, it.phone).joinToString(" · ")
            }
                .ifEmpty { listOf(stringResource(R.string.no_caregivers)) }
        )
    }
}

/** The structured address with its access details (G13), one line per kind of detail. */
@Composable
private fun addressLines(senior: SeniorPage): List<String> {
    val place = listOfNotNull(
        listOfNotNull(senior.street, senior.streetNumber).joinToString(" ").ifBlank { null },
        senior.block?.let { stringResource(R.string.address_block, it) },
        senior.staircase?.let { stringResource(R.string.address_staircase, it) },
        senior.floor?.let { stringResource(R.string.address_floor, it) },
        senior.apartment?.let { stringResource(R.string.address_apartment, it) }
    ).joinToString(", ")
    return listOfNotNull(
        place.ifBlank { null },
        senior.intercomCode?.let { stringResource(R.string.address_intercom, it) },
        senior.keyHolder?.let { stringResource(R.string.address_key_holder, it) },
        senior.landmark?.let { stringResource(R.string.address_landmark, it) }
    ).ifEmpty { listOf(stringResource(R.string.no_address)) }
}

@Composable
private fun Section(title: Int, lines: List<String>) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(stringResource(title), style = MaterialTheme.typography.titleSmall)
        lines.forEach { Text(it) }
    }
}
