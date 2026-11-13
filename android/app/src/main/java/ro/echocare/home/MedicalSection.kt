package ro.echocare.home

import android.content.ActivityNotFoundException
import android.content.ContentResolver
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import ro.echocare.MedicalItem
import ro.echocare.MedicalRecord
import ro.echocare.R
import ro.echocare.ui.Kind
import ro.echocare.ui.Rule
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.SnTextField
import ro.echocare.ui.theme.Palette

/**
 * The bytes of [uri], or null when it cannot be read. Stops one byte past [MAX_PDF_BYTES], so a
 * huge file is never held whole; the caller refuses a result over the limit.
 */
suspend fun readPdf(resolver: ContentResolver, uri: Uri): ByteArray? = withContext(Dispatchers.IO) {
    try {
        resolver.openInputStream(uri)?.use { input ->
            val out = ByteArrayOutputStream()
            val buffer = ByteArray(64 * 1024)
            while (out.size() <= MAX_PDF_BYTES) {
                val n = input.read(buffer)
                if (n < 0) break
                out.write(buffer, 0, n)
            }
            out.toByteArray()
        }
    } catch (e: java.io.IOException) {
        null
    } catch (e: SecurityException) {
        null
    }
}

/** Opens the system file picker for a PDF; [onRead] gets its bytes, or null if unreadable. */
@Composable
fun rememberPdfPicker(onRead: (ByteArray?) -> Unit): () -> Unit {
    val resolver = LocalContext.current.contentResolver
    val scope = rememberCoroutineScope()
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) scope.launch { onRead(readPdf(resolver, uri)) }
    }
    return { launcher.launch("application/pdf") }
}

/**
 * „Fișa medicală” on the medic's page: the PDF, the analysis state, and the questions to
 * confirm (design §5.7). Items are read-only once confirmed until „Modifică”.
 */
@Composable
fun MedicalSection(
    record: MedicalRecord?,
    seniorState: String,
    busy: Boolean,
    uploadNotice: Int?,
    onUpload: (ByteArray) -> Unit,
    onConfirm: (List<MedicalItem>) -> Unit,
    onReanalyze: () -> Unit
) {
    val context = LocalContext.current
    val stage = stageOf(record, seniorState)
    val pick = rememberPdfPicker { bytes -> bytes?.let(onUpload) }
    var items by remember(record?.items) { mutableStateOf(record?.items.orEmpty()) }
    var editing by remember(record?.state) { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().padding(top = 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        SectionLabel(stringResource(R.string.medical_section))
        Rule()
        stageLine(stage)?.let { Text(stringResource(it), color = Palette.FgSoft) }
        uploadNotice?.let { Text(stringResource(it), color = Palette.GalbenFg) }
        if (stage == MedicalStage.Review || stage == MedicalStage.Confirmed) {
            val open = stage == MedicalStage.Review || editing
            items.forEachIndexed { i, item ->
                ItemRow(item, editable = open && !busy) {
                    items =
                        items.toMutableList().also { l -> l[i] = it }
                }
                Rule(strong = false)
            }
            if (stage == MedicalStage.Review || editing) {
                SnButton(
                    stringResource(R.string.medical_confirm),
                    { onConfirm(items) },
                    kind = Kind.Success,
                    enabled = !busy && canConfirm(items)
                )
            } else {
                SnButton(stringResource(R.string.medical_edit), {
                    editing = true
                }, kind = Kind.Outline)
            }
        }
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            record?.pdfUrl?.let { url ->
                SnButton(stringResource(R.string.medical_open), {
                    try {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                    } catch (e: ActivityNotFoundException) {
                        // No browser to hand the link to
                    }
                }, kind = Kind.Link)
            }
            if (stage in setOf(MedicalStage.Review, MedicalStage.Confirmed, MedicalStage.Failed)) {
                SnButton(
                    stringResource(R.string.medical_reanalyze),
                    onReanalyze,
                    kind = Kind.Outline,
                    enabled = !busy
                )
            }
            SnButton(
                stringResource(
                    if (record ==
                        null
                    ) {
                        R.string.medical_upload
                    } else {
                        R.string.medical_replace
                    }
                ),
                pick,
                kind = Kind.Outline,
                enabled = !busy
            )
        }
    }
}

private fun stageLine(stage: MedicalStage): Int? = when (stage) {
    MedicalStage.WaitingForDas -> R.string.medical_waiting
    MedicalStage.Analyzing -> R.string.medical_analyzing
    MedicalStage.Review -> R.string.medical_review
    MedicalStage.Failed -> R.string.medical_failed
    MedicalStage.None, MedicalStage.Confirmed -> null
}

/** One condition: its name, the worry, the include box and the question the call will ask. */
@Composable
private fun ItemRow(item: MedicalItem, editable: Boolean, onChange: (MedicalItem) -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                item.included,
                { onChange(item.copy(included = it)) },
                enabled = editable,
                colors = CheckboxDefaults.colors(checkedColor = Palette.Link)
            )
            Text(item.condition, style = MaterialTheme.typography.titleMedium)
        }
        Text(
            "${stringResource(R.string.medical_worrying)}: ${item.worrying}",
            Modifier.padding(start = 12.dp),
            color = Palette.FgSoft
        )
        if (item.evidence.isNotBlank()) {
            Text(item.evidence, Modifier.padding(start = 12.dp), color = Palette.FgMuted)
        }
        if (editable) {
            SnTextField(
                item.question,
                { onChange(item.copy(question = it)) },
                stringResource(R.string.medical_question),
                KeyboardType.Text,
                mono = false,
                singleLine = false
            )
        } else {
            Text(item.question, Modifier.border(1.dp, Palette.Line).padding(8.dp))
        }
    }
}
