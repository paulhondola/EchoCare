package ro.echocare.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ro.echocare.EchoCareApi
import ro.echocare.R
import ro.echocare.SeniorRow
import ro.echocare.push.NotificationsPrompt
import ro.echocare.ui.Banner
import ro.echocare.ui.Chip
import ro.echocare.ui.Kind
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

/**
 * The medic's seniors for her home and Monitorizare (UC-12, design 2026-11-13 medic home):
 * GET /seniors?role=medic (04 §2). `hiltViewModel()` is scoped to the nav entry, so each of those
 * destinations has its own instance. [selected] is Monitorizare's chosen patient, kept in
 * [SavedStateHandle] so a rotation or a process death keeps it.
 */
@HiltViewModel
class MedicViewModel @Inject constructor(
    private val api: EchoCareApi,
    private val saved: SavedStateHandle
) : ViewModel() {
    var seniors by mutableStateOf<Load<List<SeniorRow>>>(Load.Loading)
        private set

    var selected by mutableStateOf(saved.get<String>("selected"))
        private set

    fun select(id: String?) {
        selected = id
        saved["selected"] = id
    }

    /** Called when a screen appears and on every timed re-read (06 §3). */
    fun reread() {
        viewModelScope.launch { seniors = seniors.after(answer { api.seniors("medic") }) }
    }
}

/**
 * The medic's home: their tasks, most important first, under the codes of their patients
 * (design 2026-11-13 medic home). A draft opens the form [onDraft], every other task the
 * patient's page [onOpen], where its action already is. [sent] shows „Trimis la DAS.” for 5 s
 * after the form submits.
 */
@Composable
fun MedicHomeScreen(
    menu: @Composable () -> Unit,
    onMonitor: () -> Unit,
    onNew: () -> Unit,
    onOpen: (String) -> Unit,
    onDraft: (String) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    sent: Boolean = false,
    onSentShown: () -> Unit = {},
    vm: MedicViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    LaunchedEffect(sent) {
        if (sent) {
            delay(5.seconds)
            onSentShown()
        }
    }
    val bar: @Composable () -> Unit = {
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            SnButton(stringResource(R.string.new_patient), onNew, kind = Kind.Success)
            menu()
        }
    }
    HomeScaffold(stringResource(R.string.medic_home), onBack = null, menu = bar) {
        LoadBody(vm.seniors, onRetry = vm::reread, onSessionEnd = onSessionEnd) { seniors ->
            val tasks = tasksOf(seniors)
            Column(Modifier.verticalScroll(rememberScrollState())) {
                // The medic's alerts (04 §6), asked for where she lands
                NotificationsPrompt()
                if (sent) Banner(stringResource(R.string.sent), Tone.Verde)
                // One column on any screen, kept readable on a tablet
                Column(
                    Modifier
                        .fillMaxWidth()
                        .wrapContentWidth(Alignment.CenterHorizontally)
                        .widthIn(max = 720.dp)
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Strip(countsOf(seniors), onMonitor)
                    SectionLabel(
                        stringResource(R.string.tasks_title, tasks.size),
                        Modifier.padding(top = 12.dp, bottom = 4.dp)
                    )
                    if (tasks.isEmpty()) {
                        Text(
                            stringResource(R.string.all_done),
                            color = Palette.FgMuted,
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                    tasks.forEach { task ->
                        val id = task.row.id
                        TaskRow(task) {
                            if (task.kind ==
                                TaskKind.Draft
                            ) {
                                onDraft(id)
                            } else {
                                onOpen(id)
                            }
                        }
                    }
                }
            }
        }
    }
}

/** The codes of her patients and those at DAS, each only above zero, and the way to all of them. */
@Composable
private fun Strip(counts: Counts, onMonitor: () -> Unit) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        itemVerticalAlignment = Alignment.CenterVertically
    ) {
        if (counts.red > 0) Chip(stringResource(R.string.count_red, counts.red), Tone.Rosu)
        if (counts.yellow > 0) {
            Chip(stringResource(R.string.count_yellow, counts.yellow), Tone.Galben)
        }
        if (counts.green > 0) Chip(stringResource(R.string.count_green, counts.green), Tone.Verde)
        if (counts.atDas > 0) Chip(stringResource(R.string.count_at_das, counts.atDas), Tone.Link)
        SnButton(stringResource(R.string.all_patients), onMonitor, kind = Kind.Link)
    }
}

/** One task: a 4dp bar by kind, who, what is waiting, and the button that goes to it. */
@Composable
private fun TaskRow(task: MedicTask, onGo: () -> Unit) {
    val (bar, line, action) = when (task.kind) {
        TaskKind.Confirm -> Triple(Palette.Link, R.string.task_confirm, R.string.do_review)
        TaskKind.AnalysisFailed -> Triple(Palette.Link, R.string.task_failed, R.string.do_open)
        TaskKind.WrongNumber ->
            Triple(Palette.Galben, R.string.task_wrong_number, R.string.do_correct)
        TaskKind.Unreachable ->
            Triple(Palette.Galben, R.string.task_unreachable, R.string.call_again)
        TaskKind.Draft -> Triple(Palette.LineStrong, R.string.task_draft, R.string.do_continue)
    }
    Row(
        Modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min)
            .background(Palette.Card),
        verticalAlignment = Alignment.CenterVertically
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
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            // A draft may not have its form of address yet
            task.row.formOfAddress.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.titleMedium)
            }
            Text(
                task.row.fullName,
                color = Palette.FgMuted,
                style = MaterialTheme.typography.bodyMedium
            )
            Text(stringResource(line), style = MaterialTheme.typography.bodyMedium)
        }
        SnButton(
            stringResource(action),
            onGo,
            Modifier.padding(end = 12.dp),
            kind = Kind.Outline
        )
    }
}
