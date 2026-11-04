package ro.echocare.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
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
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

/**
 * The medic's seniors, shared by her home, Înregistrare and Monitorizare (UC-12, UC-01):
 * GET /seniors?role=medic (04 §2).
 */
@HiltViewModel
class MedicViewModel @Inject constructor(private val api: EchoCareApi) : ViewModel() {
    var seniors by mutableStateOf<Load<List<SeniorRow>>>(Load.Loading)
        private set

    /** Called when a screen appears and on every timed re-read (06 §3). */
    fun reread() {
        viewModelScope.launch { seniors = seniors.after(answer { api.seniors("medic") }) }
    }
}

/**
 * The medic's home: two tiles, Monitorizare with what needs her and Înregistrare with her drafts
 * (UC-12, UC-01). [sent] shows „Trimis la DAS.” for 5 s after the form submits.
 */
@Composable
fun MedicHomeScreen(
    menu: @Composable () -> Unit,
    onMonitor: () -> Unit,
    onRegister: () -> Unit,
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
    HomeScaffold(stringResource(R.string.medic_home), onBack = null, menu = menu) {
        LoadBody(vm.seniors, onRetry = vm::reread, onSessionEnd = onSessionEnd) { seniors ->
            val counts = countsOf(seniors)
            Column(Modifier.verticalScroll(rememberScrollState())) {
                // The medic's alerts (04 §6), asked for where she lands
                NotificationsPrompt()
                if (sent) Banner(stringResource(R.string.sent), Tone.Verde)
                BoxWithConstraints(Modifier.padding(16.dp)) {
                    val monitor: @Composable (Modifier) -> Unit = { m ->
                        Tile(stringResource(R.string.monitor), onMonitor, m) {
                            if (counts.red > 0) {
                                Chip(stringResource(R.string.count_red, counts.red), Tone.Rosu)
                            }
                            if (counts.yellow > 0) {
                                Chip(
                                    stringResource(R.string.count_yellow, counts.yellow),
                                    Tone.Galben
                                )
                            }
                            if (counts.toResolve > 0) {
                                Chip(
                                    stringResource(R.string.count_to_resolve, counts.toResolve),
                                    Tone.Link
                                )
                            }
                        }
                    }
                    val register: @Composable (Modifier) -> Unit = { m ->
                        Tile(stringResource(R.string.register), onRegister, m) {
                            Text(
                                if (counts.drafts > 0) {
                                    stringResource(R.string.drafts_left, counts.drafts)
                                } else {
                                    stringResource(R.string.new_patient)
                                },
                                color = Palette.FgMuted,
                                style = MaterialTheme.typography.bodyMedium
                            )
                        }
                    }
                    if (maxWidth >= 600.dp) {
                        Row(
                            Modifier.height(IntrinsicSize.Min),
                            horizontalArrangement = Arrangement.spacedBy(16.dp)
                        ) {
                            monitor(Modifier.weight(1f).fillMaxHeight())
                            register(Modifier.weight(1f).fillMaxHeight())
                        }
                    } else {
                        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            monitor(Modifier)
                            register(Modifier)
                        }
                    }
                }
            }
        }
    }
}

/** A big tile: card, 2dp rule border, the title flush left, [content] under it. */
@Composable
private fun Tile(
    title: String,
    onClick: () -> Unit,
    modifier: Modifier,
    content: @Composable () -> Unit
) {
    Column(
        modifier
            .fillMaxWidth()
            .background(Palette.Card)
            .border(2.dp, Palette.Line)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(title, style = MaterialTheme.typography.headlineSmall)
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) { content() }
    }
}
