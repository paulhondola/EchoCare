package ro.echocare.enroll

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import ro.echocare.Caregiver
import ro.echocare.R
import ro.echocare.home.Failure
import ro.echocare.home.HomeScaffold
import ro.echocare.home.Load
import ro.echocare.home.LoadBody
import ro.echocare.home.SeniorDetails
import ro.echocare.home.signable
import ro.echocare.ui.Kind
import ro.echocare.ui.Rule
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.SnTextField
import ro.echocare.ui.formatPhone
import ro.echocare.ui.theme.Mono
import ro.echocare.ui.theme.Palette

/**
 * „Pacient nou”: the medic's four steps (seniors §9). Full screen on a phone and a tablet (SE20).
 * [onSubmitted] returns to the home, [onDone] to the senior's page.
 */
@Composable
fun EnrollScreen(
    onLeave: () -> Unit,
    onSubmitted: () -> Unit,
    onDone: (String) -> Unit,
    onSessionEnd: (Failure) -> Unit,
    vm: EnrollViewModel = hiltViewModel()
) {
    val back = { if (!vm.back()) onLeave() }
    BackHandler(onBack = back)
    LaunchedEffect(vm.submitted) { if (vm.submitted) onSubmitted() }
    val title = vm.saved[Field.FormOfAddress]?.takeIf { vm.existing && it.isNotBlank() }
        ?: stringResource(R.string.new_patient)
    HomeScaffold(title, onBack = back, menu = {}) {
        LoadBody(vm.form, onRetry = vm::open, onSessionEnd = onSessionEnd) {
            Steps(vm, onDone, onSessionEnd)
        }
    }
}

/** One column, at most 600dp wide and centred on a tablet, full width on a phone (seniors §9.4). */
@Composable
private fun Steps(vm: EnrollViewModel, onDone: (String) -> Unit, onSessionEnd: (Failure) -> Unit) {
    val scroll = rememberScrollState()
    LaunchedEffect(vm.step) { scroll.scrollTo(0) }
    BoxWithConstraints(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        val wide = maxWidth >= 600.dp
        Column(
            Modifier
                .widthIn(max = 600.dp)
                .fillMaxWidth()
                .verticalScroll(scroll)
                .padding(horizontal = 16.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            StepHeader(vm.step, wide)
            when (vm.step) {
                Step.Senior, Step.Address -> Fields(vm, vm.step.fields, vm.values)
                Step.Caregivers -> CaregiversStep(vm)
                Step.Review -> ReviewStep(vm, onSessionEnd)
            }
            vm.notice?.let { NoticeLine(it) }
            Buttons(vm, onDone)
        }
    }
}

/** „Pasul 2 din 4” and the step's name; on a wide screen, all four with this one marked. */
@Composable
private fun StepHeader(step: Step, wide: Boolean) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionLabel(stringResource(R.string.step_counter, step.ordinal + 1, Step.entries.size))
        if (wide) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                Step.entries.forEach { StepName(it, current = it == step) }
            }
        } else {
            Text(
                stringResource(step.title),
                Modifier.semantics { heading() },
                style = MaterialTheme.typography.titleLarge
            )
        }
        Rule()
    }
}

@Composable
private fun StepName(step: Step, current: Boolean) {
    Column(Modifier.width(IntrinsicSize.Max), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            stringResource(step.title),
            if (current) Modifier.semantics { heading() } else Modifier,
            color = if (current) Palette.Fg else Palette.FgMuted,
            style = MaterialTheme.typography.titleMedium
        )
        Box(
            Modifier
                .fillMaxWidth()
                .height(2.dp)
                .background(if (current) Palette.Link else Palette.Canvas)
        )
    }
}

/** Text fields. A field over its limit says so; the server's refusals say the rest (§9.3). */
@Composable
private fun Fields(vm: EnrollViewModel, fields: List<Field>, values: Map<Field, String>) {
    val problems = problems(values, fields, vm.draft)
    fields.forEach { field ->
        val tooLong = problems[field] == Problem.TooLong
        SnTextField(
            values[field].orEmpty(),
            { vm.type(field, it) },
            stringResource(field.label),
            if (field.phone) KeyboardType.Phone else KeyboardType.Text,
            mono = field.phone,
            hint = if (field == Field.FormOfAddress) {
                stringResource(R.string.form_of_address_hint)
            } else {
                null
            },
            error = vm.errors[field]?.let { stringResource(it) }
                ?: if (tooLong) stringResource(R.string.too_long, field.max ?: 0) else null,
            capitalization = when (field) {
                Field.FullName, Field.CaregiverName -> KeyboardCapitalization.Words
                Field.Street, Field.KeyHolder, Field.Landmark -> KeyboardCapitalization.Sentences
                else -> KeyboardCapitalization.None
            }
        )
    }
}

/** Step 3: the caregivers so far, and a row to add one. Each button calls the API at once. */
@Composable
private fun CaregiversStep(vm: EnrollViewModel) {
    Column {
        if (vm.caregivers.isEmpty()) {
            Text(
                stringResource(R.string.no_caregivers),
                Modifier.padding(vertical = 12.dp),
                color = Palette.FgMuted
            )
        }
        vm.caregivers.forEachIndexed { i, c ->
            CaregiverRow(c, enabled = !vm.busy, onRemove = { vm.remove(c) })
            Rule(strong = i == vm.caregivers.lastIndex)
        }
    }
    Text(
        stringResource(R.string.new_caregiver),
        Modifier.semantics { heading() },
        style = MaterialTheme.typography.titleMedium
    )
    Fields(vm, Step.Caregivers.fields, vm.adding)
    SnButton(
        stringResource(R.string.add),
        vm::add,
        kind = Kind.Link,
        enabled = !vm.busy && problems(vm.adding, Step.Caregivers.fields, vm.draft).isEmpty()
    )
}

@Composable
private fun CaregiverRow(caregiver: Caregiver, enabled: Boolean, onRemove: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                listOfNotNull(caregiver.displayName, caregiver.relation).joinToString(" · "),
                style = MaterialTheme.typography.titleMedium
            )
            Text(formatPhone(caregiver.phone), style = Mono, color = Palette.FgSoft)
        }
        SnButton(stringResource(R.string.remove), onRemove, kind = Kind.Outline, enabled = enabled)
    }
}

/** Step 4: the senior as GET seniors/{id} has them, and what submitting still needs. */
@Composable
private fun ReviewStep(vm: EnrollViewModel, onSessionEnd: (Failure) -> Unit) {
    LoadBody(vm.review, onRetry = vm::reread, onSessionEnd = onSessionEnd) { senior ->
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            // A refused submit names what is missing itself, over the buttons
            val missing = missingOf(senior)
            if (senior.state == "draft" && missing.isNotEmpty() && vm.notice !is Notice.Missing) {
                NoticeLine(Notice.Missing(missing))
            }
            SeniorDetails(senior, callSenior = false, calls = false)
            if (signable(senior)) {
                ConsentSection(senior.signedAt, vm.busy) { strokes, w, h -> vm.sign(strokes, w, h) }
            }
        }
    }
}

@Composable
private fun NoticeLine(notice: Notice) {
    val text = when (notice) {
        is Notice.Says -> stringResource(notice.text)

        is Notice.Missing -> stringResource(
            R.string.missing,
            notice.names.map { name -> MISSING_LABELS[name]?.let { stringResource(it) } ?: name }
                .joinToString(", ")
        )
    }
    Text(text, color = Palette.GalbenFg, style = MaterialTheme.typography.bodyLarge)
}

/** „Înapoi” from step 2 on, then „Continuă”, or on step 4 „Trimite la DAS” or „Gata”. */
@Composable
private fun Buttons(vm: EnrollViewModel, onDone: (String) -> Unit) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        if (vm.step != Step.Senior) {
            SnButton(
                stringResource(R.string.back),
                { vm.back() },
                kind = Kind.Outline,
                enabled = !vm.busy
            )
        }
        if (vm.step != Step.Review) {
            SnButton(
                stringResource(R.string.next_step),
                vm::next,
                kind = Kind.Link,
                enabled = !vm.busy && canContinue(vm.step, vm.values, vm.draft)
            )
            return@FlowRow
        }
        val senior = (vm.review as? Load.Ready)?.value ?: return@FlowRow
        if (senior.state == "draft") {
            SnButton(
                stringResource(R.string.submit),
                vm::submit,
                kind = Kind.Success,
                enabled = !vm.busy && missingOf(senior).isEmpty() && vm.notice !is Notice.Missing
            )
        } else {
            SnButton(stringResource(R.string.done), { onDone(senior.id) }, kind = Kind.Link)
        }
    }
}
