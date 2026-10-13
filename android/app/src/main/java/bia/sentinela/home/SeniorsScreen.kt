package bia.sentinela.home

import androidx.annotation.StringRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import bia.sentinela.R
import bia.sentinela.SeniorRow

/** The medic's and the caregiver's home: their seniors as cards (seniors §8.2, SE20). */
@Composable
fun SeniorsScreen(
    @StringRes title: Int,
    menu: @Composable () -> Unit,
    onOpen: (String) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: SeniorsViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    HomeScaffold(stringResource(title), onBack = null, menu = menu) {
        LoadBody(vm.seniors, onRetry = vm::reread, onSessionEnd = onSessionEnd) { seniors ->
            if (seniors.isEmpty()) {
                Message(stringResource(R.string.no_seniors))
            } else {
                // One column on a phone, two or more on a tablet.
                LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 320.dp),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(seniors, key = { it.id }) { senior ->
                        SeniorCard(senior, onClick = { onOpen(senior.id) })
                    }
                }
            }
        }
    }
}

@Composable
private fun SeniorCard(senior: SeniorRow, onClick: () -> Unit) {
    OutlinedCard(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(senior.formOfAddress, style = MaterialTheme.typography.titleMedium)
            Text(
                "${senior.fullName} · ${senior.phone}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            StateLabel(senior.state)
        }
    }
}

/** The enrollment state as a small outlined label; nothing for a state this build does not know. */
@Composable
fun StateLabel(state: String) {
    val label = STATE_LABELS[state] ?: return
    Surface(
        shape = MaterialTheme.shapes.small,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline)
    ) {
        Text(
            stringResource(label),
            Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelMedium
        )
    }
}
