package ro.echocare.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import java.time.Instant
import ro.echocare.R
import ro.echocare.SeniorRow
import ro.echocare.ui.Kind
import ro.echocare.ui.Rule
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton

/** The unfinished enrollments, the newest first; one with no readable `createdAt` goes last (UC-01). */
fun draftsNewestFirst(rows: List<SeniorRow>): List<SeniorRow> =
    rows.filter { it.state == "draft" }.sortedByDescending {
        it.createdAt?.let { t -> runCatching { Instant.parse(t) }.getOrNull() } ?: Instant.MIN
    }

/**
 * Înregistrare: „Pacient nou” and the drafts to finish, each opening the form filled in
 * (UC-01, seniors §9.1).
 */
@Composable
fun RegisterScreen(
    onBack: () -> Unit,
    menu: @Composable () -> Unit,
    onNew: () -> Unit,
    onDraft: (String) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: MedicViewModel = hiltViewModel()
) {
    RereadWhileShown(vm::reread)
    HomeScaffold(stringResource(R.string.register), onBack = onBack, menu = menu) {
        LoadBody(vm.seniors, onRetry = vm::reread, onSessionEnd = onSessionEnd) { seniors ->
            val drafts = draftsNewestFirst(seniors)
            Column(
                Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                SnButton(stringResource(R.string.new_patient), onNew, kind = Kind.Link)
                if (drafts.isNotEmpty()) {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SectionLabel(stringResource(R.string.drafts))
                        Rule()
                        drafts.forEach { d ->
                            SnButton(
                                d.fullName,
                                { onDraft(d.id) },
                                Modifier.fillMaxWidth()
                            )
                        }
                    }
                }
            }
        }
    }
}
