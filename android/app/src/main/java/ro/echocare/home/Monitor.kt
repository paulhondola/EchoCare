package ro.echocare.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import java.time.Instant
import ro.echocare.R
import ro.echocare.SeniorRow
import ro.echocare.das.ago
import ro.echocare.das.agoText
import ro.echocare.ui.Chip
import ro.echocare.ui.Kind
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

/** Width from which Monitorizare shows the list and the patient side by side (UC-12). */
const val TWO_PANE_MIN = 840

/**
 * Monitorizare: the medic's patients by need, and on a tablet the chosen patient beside them
 * (UC-12, 03 §7). On a phone a tap opens the patient's own page through [onOpen].
 */
@Composable
fun MonitorScreen(
    onBack: () -> Unit,
    menu: @Composable () -> Unit,
    onOpen: (String) -> Unit,
    onRegister: () -> Unit,
    onEdit: (String) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: MedicViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    HomeScaffold(stringResource(R.string.monitor), onBack = onBack, menu = menu) {
        if (vm.seniors == Load.Loading) {
            PlaceholderCards(6)
            return@HomeScaffold
        }
        LoadBody(vm.seniors, onRetry = vm::reread, onSessionEnd = onSessionEnd) { seniors ->
            val groups = panel(seniors)
            if (groups.isEmpty()) {
                Message(stringResource(R.string.no_patients_yet)) {
                    SnButton(stringResource(R.string.register), onRegister)
                }
                return@LoadBody
            }
            BoxWithConstraints(Modifier.fillMaxSize()) {
                if (maxWidth.value >= TWO_PANE_MIN) {
                    Row(Modifier.fillMaxSize()) {
                        PatientList(
                            groups,
                            vm.selected,
                            vm::select,
                            Modifier
                                .weight(0.4f)
                                .fillMaxHeight()
                        )
                        Box(
                            Modifier
                                .width(2.dp)
                                .fillMaxHeight()
                                .background(Palette.Line)
                        )
                        Box(
                            Modifier
                                .weight(0.6f)
                                .fillMaxHeight()
                        ) {
                            val id = vm.selected
                            if (id == null) {
                                Message(stringResource(R.string.pick_patient))
                            } else {
                                // One page per patient, so a new choice starts clean
                                key(id) {
                                    PatientPane(id, onSessionEnd, onEdit)
                                }
                            }
                        }
                    }
                } else {
                    PatientList(groups, null, onOpen, Modifier.fillMaxSize())
                }
            }
        }
    }
}

@Composable
private fun PatientList(
    groups: List<Pair<Group, List<SeniorRow>>>,
    selected: String?,
    onPick: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var showInactive by rememberSaveable { mutableStateOf(false) }
    val now = Instant.now()
    LazyColumn(
        modifier,
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        groups.forEach { (group, rows) ->
            item(key = "label-${group.name}") {
                SectionLabel(
                    stringResource(group.title),
                    Modifier.padding(top = 12.dp, bottom = 4.dp)
                )
            }
            // Inactive starts collapsed: those patients need nothing from her
            val collapsed = group == Group.Inactive && !showInactive
            if (!collapsed) {
                items(rows, key = { it.id }) { row ->
                    PatientCard(row, group, row.id == selected, now) { onPick(row.id) }
                }
            }
            if (group == Group.Inactive) {
                item(key = "toggle") {
                    SnButton(
                        if (showInactive) {
                            stringResource(R.string.hide)
                        } else {
                            stringResource(R.string.show_n, rows.size)
                        },
                        { showInactive = !showInactive },
                        kind = Kind.Link
                    )
                }
            }
        }
    }
}

/** One patient: a 4dp bar and tint by need, who, why, since when (UC-12, 03 §7). */
@Composable
fun PatientCard(
    row: SeniorRow,
    group: Group,
    selected: Boolean,
    now: Instant,
    onClick: () -> Unit
) {
    val yellow = row.code == "yellow"
    val (bar, tint) = when {
        group == Group.Urgent && yellow -> Palette.Galben to Tone.Galben.fill
        group == Group.Urgent -> Palette.Rosu to Tone.Rosu.fill
        group == Group.ToResolve -> Palette.Link to Palette.Card
        else -> Palette.Line to Palette.Card
    }
    Row(
        Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min)
            .alpha(if (group == Group.Inactive) 0.6f else 1f)
            .background(tint)
            .border(2.dp, if (selected) Palette.Link else Color.Transparent)
            .clickable(role = Role.Button, onClick = onClick)
    ) {
        Box(
            Modifier
                .width(4.dp)
                .fillMaxHeight()
                .background(bar)
        )
        Column(
            Modifier
                .weight(1f)
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            if (row.state == "active" && row.code != null) {
                CodeLabel(row.code, row.reason)
            } else {
                StateLabel(row.state)
            }
            Text(row.formOfAddress, style = MaterialTheme.typography.titleMedium)
            Text(
                row.fullName,
                color = Palette.FgMuted,
                style = MaterialTheme.typography.bodyMedium
            )
            says(row)?.let {
                Text(stringResource(it), style = MaterialTheme.typography.bodyMedium)
            }
            val at = when (group) {
                Group.Urgent -> row.since
                Group.AtDas -> row.submittedAt
                else -> null
            }
            at?.let { iso ->
                runCatching { ago(iso, now) }.getOrNull()?.let {
                    Text(
                        agoText(it),
                        color = Palette.FgMuted,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
            watchChip(row.watchState)?.takeIf { row.watchState != "ok" }?.let { (label, tone) ->
                Chip(stringResource(label), tone)
            }
        }
    }
}

// The state in the medic's words, for the states that need her (UC-12).
private fun says(row: SeniorRow): Int? = when (row.state) {
    "wrong_number" -> R.string.says_wrong_number
    "unreachable" -> R.string.says_unreachable
    "accepted" -> R.string.says_welcome_pending
    else -> null
}

/** Grey boxes where the cards will be while the list loads: no spinner (UC-12). */
@Composable
fun PlaceholderCards(count: Int) {
    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        repeat(count) {
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(88.dp)
                    .background(Palette.Card)
            )
        }
    }
}
