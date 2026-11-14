import Foundation

// The medic's medical record section (design §5.7), ported from android/app/.../home/Medical.kt.

let MAX_PDF_BYTES = 10 * 1024 * 1024

/// What the section shows.
enum MedicalStage: Equatable {
    case none, waitingForDas, analyzing, notAnalyzed, review, confirmed, failed
}

/// The stage of `record` for a senior in `seniorState`; an unknown record state reads as
/// analyzing. The server analyzes only `accepted` and `active` seniors (design §5.3).
func stageOf(_ record: MedicalRecord?, seniorState: String) -> MedicalStage {
    guard let record else { return .none }
    switch record.state {
    case "pending":
        switch seniorState {
        case "draft", "submitted": return .waitingForDas
        case "accepted", "active": return .analyzing
        default: return .notAnalyzed
        }
    case "review": return .review
    case "confirmed": return .confirmed
    case "failed": return .failed
    default: return .analyzing
    }
}

/// The server refuses an empty question, so an excluded item the medic blanked sends its `stored`
/// one; an included blank is stopped by `canConfirm`.
func confirmFormOf(_ edited: [MedicalItem], stored: [MedicalItem], analyzedAt: String? = nil) -> MedicalConfirmForm {
    let items = edited.enumerated().map { i, item in
        let question = item.question.trimmingCharacters(in: .whitespacesAndNewlines)
        let worry = item.worrying.trimmingCharacters(in: .whitespacesAndNewlines)
        return ConfirmItem(
            included: item.included,
            question: question.isEmpty && !item.included ? (i < stored.count ? stored[i].question : question) : question,
            // A blank worry keeps the stored one
            worrying: worry.isEmpty ? nil : worry)
    }
    return MedicalConfirmForm(items: items, analyzedAt: analyzedAt)
}

func canConfirm(_ items: [MedicalItem]) -> Bool {
    items.allSatisfy { !$0.included || !$0.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
}

/// Reanalyzing drops a confirmed profile and its checks, so there it waits for „Modifică”.
func canReanalyze(_ stage: MedicalStage, editing: Bool) -> Bool {
    stage == .review || stage == .failed || (stage == .confirmed && editing)
}
