package ro.echocare.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import ro.echocare.R
import ro.echocare.SeniorRow
import ro.echocare.push.NotificationsPrompt
import ro.echocare.ui.Chip
import ro.echocare.ui.PhoneNumber
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

/**
 * The caregiver's home: their seniors as cards (seniors §8.2, SE20). The medic
 * has their own home now (MedicHome.kt, UC-12).
 */
@Composable
fun SeniorsScreen(
    menu: @Composable () -> Unit,
    onOpen: (SeniorRow) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: SeniorsViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    HomeScaffold(stringResource(R.string.caregiver_home), onBack = null, menu = menu) {
        LoadBody(vm.seniors, onRetry = vm::reread, onSessionEnd = onSessionEnd) { seniors ->
            // The caregiver's alerts (04 §6), asked for where they land
            NotificationsPrompt()
            if (seniors.isEmpty()) {
                Message(stringResource(R.string.no_seniors))
            } else {
                // One column on a phone, two or more on a tablet.
                LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 320.dp),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(seniors, key = { it.id }) { senior ->
                        SeniorCard(senior, onClick = { onOpen(senior) })
                    }
                }
            }
        }
    }
}

/** The dashboard's card: a bar down the left edge in the code's colour, else the state's. */
@Composable
private fun SeniorCard(senior: SeniorRow, onClick: () -> Unit) {
    val tone = CODE_TONES[senior.code] ?: STATE_TONES[senior.state] ?: Tone.Muted
    Row(
        Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min)
            .background(Palette.Card)
            .border(1.dp, Palette.Line)
            .clickable(role = Role.Button, onClick = onClick)
    ) {
        Box(
            Modifier
                .width(3.dp)
                .fillMaxHeight()
                .background(tone.dot)
        )
        Column(
            Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(senior.formOfAddress, style = MaterialTheme.typography.titleMedium)
            Text(
                senior.fullName,
                color = Palette.FgMuted,
                style = MaterialTheme.typography.bodyMedium
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                PhoneNumber(senior.phone, senior.landline)
            }
            StateLabel(senior.state)
            CodeLabel(senior.code, senior.reason)
        }
    }
}

/** The enrollment state as a tinted chip; nothing for a state this build does not know. */
@Composable
fun StateLabel(state: String) {
    val label = STATE_LABELS[state] ?: return
    Chip(stringResource(label), STATE_TONES[state] ?: Tone.Muted)
}

/** The code as a tinted chip with its reason; nothing for a code this build does not know (Q17). */
@Composable
fun CodeLabel(code: String?, reason: String?) {
    val label = CODE_LABELS[code] ?: return
    Row(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Chip(stringResource(label), CODE_TONES[code] ?: Tone.Muted)
        reason?.let {
            Text(it, color = Palette.FgMuted, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
