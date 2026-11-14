package ro.echocare.das

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import ro.echocare.R
import ro.echocare.home.Failure
import ro.echocare.home.HomeScaffold
import ro.echocare.ui.Kind
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.SnTextField
import ro.echocare.ui.theme.Mono
import ro.echocare.ui.theme.Palette

/** „Rezolvare caz”: one of five outcomes and a short note (UC-11 step 4, 04 §2). */
@Composable
fun ResolveScreen(
    onBack: () -> Unit,
    onDone: () -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: ResolveViewModel = hiltViewModel()
) {
    val ended = (vm.notice as? Notice.Ends)?.failure
    LaunchedEffect(ended) { ended?.let(onSessionEnd) }
    LaunchedEffect(vm.done) { if (vm.done) onDone() }
    HomeScaffold(stringResource(R.string.resolve_title), onBack = onBack, menu = {}) {
        Column(Modifier.fillMaxSize()) {
            Column(
                Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 20.dp)
                    .widthIn(max = 600.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                SectionLabel(stringResource(R.string.resolve_outcome))
                Column(
                    Modifier.selectableGroup(),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OUTCOMES.forEach { (value, label) ->
                        val picked = vm.outcome == value
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .border(1.dp, if (picked) Palette.Link else Palette.Line)
                                .selectable(picked, role = Role.RadioButton) { vm.outcome = value }
                                .heightIn(min = 48.dp)
                                .padding(horizontal = 12.dp),
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            // The dashboard's square marker, not Material's round one
                            Box(
                                Modifier
                                    .size(14.dp)
                                    .background(if (picked) Palette.Link else Color.Transparent)
                                    .border(2.dp, if (picked) Palette.Link else Palette.LineStrong)
                            )
                            Text(stringResource(label), style = MaterialTheme.typography.bodyLarge)
                        }
                    }
                }
                SnTextField(
                    vm.note,
                    // A paste past the limit is cut, as the dashboard's maxlength
                    { vm.note = it.take(NOTE_MAX) },
                    stringResource(R.string.resolve_note),
                    KeyboardType.Text,
                    Modifier.padding(top = 12.dp),
                    mono = false,
                    capitalization = KeyboardCapitalization.Sentences,
                    singleLine = false
                )
                Text(
                    stringResource(R.string.note_count, vm.note.length, NOTE_MAX),
                    Modifier.align(Alignment.End),
                    color = Palette.FgMuted,
                    style = Mono
                )
            }
            vm.notice?.let { NoticeBanner(it) }
            ActionBar {
                SnButton(
                    stringResource(R.string.send),
                    vm::submit,
                    Modifier.fillMaxWidth(),
                    kind = Kind.Success,
                    enabled = canSend(vm.outcome, vm.note) && !vm.sending
                )
            }
        }
    }
}
