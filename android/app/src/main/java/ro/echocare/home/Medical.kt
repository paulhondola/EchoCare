package ro.echocare.home

import ro.echocare.ConfirmItem
import ro.echocare.MedicalConfirmForm
import ro.echocare.MedicalItem
import ro.echocare.MedicalRecord

// The medic's medical record section (design §5.7). Pure, tested on the JVM.

const val MAX_PDF_BYTES = 10 * 1024 * 1024

/** What the section shows. */
enum class MedicalStage { None, WaitingForDas, Analyzing, Review, Confirmed, Failed }

/** The stage of [record] for a senior in [seniorState]; an unknown state reads as analyzing. */
fun stageOf(record: MedicalRecord?, seniorState: String): MedicalStage = when (record?.state) {
    null -> MedicalStage.None
    "pending" ->
        if (seniorState == "draft" || seniorState == "submitted") {
            MedicalStage.WaitingForDas
        } else {
            MedicalStage.Analyzing
        }
    "review" -> MedicalStage.Review
    "confirmed" -> MedicalStage.Confirmed
    "failed" -> MedicalStage.Failed
    else -> MedicalStage.Analyzing
}

fun confirmFormOf(items: List<MedicalItem>) =
    MedicalConfirmForm(items.map { ConfirmItem(it.included, it.question.trim()) })

fun canConfirm(items: List<MedicalItem>) = items.all { !it.included || it.question.isNotBlank() }
