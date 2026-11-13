package ro.echocare.home

import ro.echocare.ConfirmItem
import ro.echocare.MedicalConfirmForm
import ro.echocare.MedicalItem
import ro.echocare.MedicalRecord

// The medic's medical record section (design §5.7). Pure, tested on the JVM.

const val MAX_PDF_BYTES = 10 * 1024 * 1024

/** What the section shows. */
enum class MedicalStage { None, WaitingForDas, Analyzing, NotAnalyzed, Review, Confirmed, Failed }

/**
 * The stage of [record] for a senior in [seniorState]; an unknown record state reads as analyzing.
 * The server analyzes only `accepted` and `active` seniors (design §5.3).
 */
fun stageOf(record: MedicalRecord?, seniorState: String): MedicalStage = when (record?.state) {
    null -> MedicalStage.None
    "pending" -> when (seniorState) {
        "draft", "submitted" -> MedicalStage.WaitingForDas
        "accepted", "active" -> MedicalStage.Analyzing
        else -> MedicalStage.NotAnalyzed
    }
    "review" -> MedicalStage.Review
    "confirmed" -> MedicalStage.Confirmed
    "failed" -> MedicalStage.Failed
    else -> MedicalStage.Analyzing
}

/**
 * The server refuses an empty question, so an excluded item the medic blanked sends its [stored]
 * one; an included blank is stopped by [canConfirm].
 */
fun confirmFormOf(edited: List<MedicalItem>, stored: List<MedicalItem>) = MedicalConfirmForm(
    edited.mapIndexed { i, it ->
        val question = it.question.trim()
        ConfirmItem(
            it.included,
            if (question.isEmpty() &&
                !it.included
            ) {
                stored.getOrNull(i)?.question ?: question
            } else {
                question
            }
        )
    }
)

fun canConfirm(items: List<MedicalItem>) = items.all { !it.included || it.question.isNotBlank() }

/** Reanalyzing drops a confirmed profile and its checks, so there it waits for „Modifică”. */
fun canReanalyze(stage: MedicalStage, editing: Boolean) = stage == MedicalStage.Review ||
    stage == MedicalStage.Failed ||
    (stage == MedicalStage.Confirmed && editing)
