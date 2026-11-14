import Foundation

// The medic home's to-do list (design 2026-11-13 medic home): what only the medic can move, most
// important first. Ported from android/app/.../home/Tasks.kt; built from the API's strings, never
// decoded, so a value this build does not know makes no task (ADR-001 §2.3).

/// The kinds of task, in their order of importance.
enum TaskKind: Int, Comparable {
    case confirm, analysisFailed, wrongNumber, unreachable, draft

    static func < (a: TaskKind, b: TaskKind) -> Bool { a.rawValue < b.rawValue }
}

struct MedicTask: Equatable {
    let row: SeniorRow
    let kind: TaskKind
}

/// A refused or withdrawn senior, or one in a state this build does not know, needs no profile.
private func wantsProfile(_ state: String) -> Bool {
    STATE_LABELS[state] != nil && state != "refused" && state != "withdrawn"
}

/// One task per senior, the most important: a profile before a welcome-call problem.
private func kindOf(_ row: SeniorRow) -> TaskKind? {
    if row.medicalRecordState == "review" && wantsProfile(row.state) { return .confirm }
    if row.medicalRecordState == "failed" && wantsProfile(row.state) { return .analysisFailed }
    switch row.state {
    case "wrong_number": return .wrongNumber
    case "unreachable": return .unreachable
    case "draft": return .draft
    default: return nil
    }
}

/// How long it has waited: a draft since it was begun, a welcome-call problem since acceptance.
private func waitingSince(_ task: MedicTask) -> Date? {
    switch task.kind {
    case .draft: instantOf(task.row.createdAt)
    case .wrongNumber, .unreachable: instantOf(task.row.acceptedAt)
    default: nil
    }
}

/// By kind, then the longest waiting first; no time last, otherwise the API's order.
func tasksOf(_ rows: [SeniorRow]) -> [MedicTask] {
    let tasks = rows.compactMap { row in kindOf(row).map { MedicTask(row: row, kind: $0) } }
    return stableSorted(tasks) { a, b in
        a.kind != b.kind
            ? (a.kind < b.kind ? -1 : 1) : oldestFirst(waitingSince(a), waitingSince(b))
    }
}
