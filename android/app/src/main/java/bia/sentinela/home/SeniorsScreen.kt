package bia.sentinela.home

import androidx.annotation.StringRes
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import bia.sentinela.R
import bia.sentinela.SeniorRow
import bia.sentinela.ui.Banner
import bia.sentinela.ui.Chip
import bia.sentinela.ui.Kind
import bia.sentinela.ui.PhoneNumber
import bia.sentinela.ui.SnButton
import bia.sentinela.ui.Tone
import bia.sentinela.ui.theme.Palette
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.delay

/**
 * The medic's and the caregiver's home: their seniors as cards (seniors §8.2, SE20). [onNew] is the
 * medic's „Pacient nou” (§9.1); [sent] shows „Trimis la DAS.” after the form submits.
 */
@Composable
fun SeniorsScreen(
    @StringRes title: Int,
    menu: @Composable () -> Unit,
    onOpen: (SeniorRow) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    onNew: (() -> Unit)? = null,
    sent: Boolean = false,
    onSentShown: () -> Unit = {},
    vm: SeniorsViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    LaunchedEffect(sent) {
        if (sent) {
            delay(5.seconds)
            onSentShown()
        }
    }
    HomeScaffold(stringResource(title), onBack = null, menu = menu) {
        LoadBody(vm.seniors, onRetry = vm::reread, onSessionEnd = onSessionEnd) { seniors ->
            if (sent) Banner(stringResource(R.string.sent), Tone.Verde)
            onNew?.let {
                SnButton(
                    stringResource(R.string.new_patient),
                    it,
                    Modifier.padding(start = 16.dp, end = 16.dp, top = 16.dp),
                    kind = Kind.Link
                )
            }
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

/** The dashboard's card: a bar in the state's colour down the left edge. */
@Composable
private fun SeniorCard(senior: SeniorRow, onClick: () -> Unit) {
    val tone = STATE_TONES[senior.state] ?: Tone.Muted
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
        }
    }
}

/** The enrollment state as a tinted chip; nothing for a state this build does not know. */
@Composable
fun StateLabel(state: String) {
    val label = STATE_LABELS[state] ?: return
    Chip(stringResource(label), STATE_TONES[state] ?: Tone.Muted)
}
