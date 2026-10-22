package ro.echocare.das

import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import ro.echocare.IncidentRow
import ro.echocare.R
import ro.echocare.home.Failure
import ro.echocare.home.HomeScaffold
import ro.echocare.home.LoadBody
import ro.echocare.home.Message
import ro.echocare.home.RereadWhileShown
import ro.echocare.ui.Chip
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

/** The DAS home: red incidents, open then in progress, the longest wait first (UC-12). */
@Composable
fun IncidentsScreen(
    menu: @Composable () -> Unit,
    onOpen: (String) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: IncidentsViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    HomeScaffold(stringResource(R.string.role_das), onBack = null, menu = menu) {
        LoadBody(vm.incidents, onRetry = vm::reread, onSessionEnd = onSessionEnd) { rows ->
            val s = sections(rows)
            if (s.open.isEmpty() && s.inProgress.isEmpty()) {
                Message(stringResource(R.string.no_incidents))
            } else {
                // Set on every re-read, so "acum …" moves on while the incidents stay the same
                val now = vm.now
                LazyColumn(
                    Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    section(R.string.incidents_open, s.open, now, onOpen)
                    section(R.string.incidents_in_progress, s.inProgress, now, onOpen)
                }
            }
        }
    }
}

private fun LazyListScope.section(
    @StringRes title: Int,
    rows: List<IncidentRow>,
    now: Instant,
    onOpen: (String) -> Unit
) {
    if (rows.isEmpty()) return
    item(key = title) {
        SectionLabel(
            stringResource(title, rows.size),
            Modifier.padding(top = 8.dp, bottom = 4.dp)
        )
    }
    items(rows, key = { it.id }) { IncidentCard(it, now, onClick = { onOpen(it.id) }) }
}

/** The dashboard's card, with a red bar: every incident is a red (G16). */
@Composable
private fun IncidentCard(row: IncidentRow, now: Instant, onClick: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Palette.Card)
            .border(1.dp, Palette.Line)
            // The bar is drawn, not a child: IntrinsicSize.Min would measure the FlowRow below
            // as one line and clip the chips it wraps
            .drawBehind { drawRect(Tone.Rosu.dot, size = Size(3.dp.toPx(), size.height)) }
            .clickable(role = Role.Button, onClick = onClick)
            .padding(start = 17.dp, end = 14.dp, top = 12.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Text(row.seniorName, style = MaterialTheme.typography.titleMedium)
        Text(row.reason, color = Palette.FgSoft, style = MaterialTheme.typography.bodyMedium)
        // Whole chips wrap to a second line on a narrow phone, never their words
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
            itemVerticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                agoText(ago(row.openedAt, now)),
                color = Palette.FgMuted,
                style = MaterialTheme.typography.bodySmall
            )
            StatusChip(row.status, row.takenByName)
            HandoverChip(row.handoverAnswered)
        }
    }
}

/** Deschis, Preluat de …, Rezolvat; a status this build does not know shows as it is. */
@Composable
fun StatusChip(status: String, takenByName: String?) {
    when (status) {
        "open" -> Chip(stringResource(R.string.status_open), Tone.Rosu)
        "in_progress" -> Chip(
            stringResource(R.string.status_taken_by, takenByName.orEmpty()),
            Tone.Link
        )
        "resolved" -> Chip(stringResource(R.string.status_resolved), Tone.Verde)
        else -> Chip(status, Tone.Muted)
    }
}

/** As the dashboard's card: whether the hand-over was answered on any of the calls (04 §1). */
@Composable
private fun HandoverChip(answered: Boolean) {
    if (answered) {
        Chip(stringResource(R.string.handover_yes), Tone.Verde)
    } else {
        Chip(stringResource(R.string.handover_no), Tone.Galben)
    }
}

private val day = DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm")

@Composable
fun agoText(ago: Ago): String = when (ago) {
    Ago.Moments -> stringResource(R.string.ago_moments)
    is Ago.Minutes -> stringResource(R.string.ago_minutes, ago.m.toInt())
    is Ago.Hours -> stringResource(R.string.ago_hours, ago.h.toInt(), ago.m.toInt())
    is Ago.On -> day.format(ago.at.atZone(ZoneId.systemDefault()))
}
