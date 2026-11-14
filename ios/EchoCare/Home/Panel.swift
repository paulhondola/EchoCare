import Foundation

// The medic's panel: the groups of her patients, the actions on one, and the enrollment stages
// (UC-12, 03 §7, UC-04). Ported from android/app/.../home/Panel.kt. PatientGroup and PatientAction
// are built here from the API's strings, never decoded: a state or code this build does not know
// must not crash. Kotlin's `Group` is `PatientGroup` here, as SwiftUI has a `Group` of its own.

enum PatientGroup: CaseIterable, Hashable {
    case urgent, toResolve, inProgress, green, atDas, inactive

    /// The section's label, a `Localizable.xcstrings` key.
    var title: String {
        switch self {
        case .urgent: "group_urgent"
        case .toResolve: "group_to_resolve"
        case .inProgress: "group_in_progress"
        case .green: "group_green"
        case .atDas: "group_at_das"
        case .inactive: "group_inactive"
        }
    }
}

/// Nil for a draft: it is not a patient of the panel yet, only counted.
func groupOf(_ row: SeniorRow) -> PatientGroup? {
    switch row.state {
    case "draft": nil
    case "active": row.code == "red" || row.code == "yellow" ? .urgent : .green
    case "wrong_number", "unreachable": .toResolve
    case "accepted": .inProgress
    case "submitted": .atDas
    default: .inactive
    }
}

/// An ISO-8601 instant, or nil for none or an unreadable one.
func instantOf(_ text: String?) -> Date? { text.flatMap(instant) }

/// Earlier first, no time last; -1, 0 or 1 as Kotlin's comparators.
func oldestFirst(_ x: Date?, _ y: Date?) -> Int {
    switch (x, y) {
    case (nil, nil): 0
    case (nil, _): 1
    case (_, nil): -1
    case let (x?, y?): x < y ? -1 : (x > y ? 1 : 0)
    }
}

/// Sorted by `compare`, keeping the given order between equals, as Kotlin's `sortedWith` does.
/// Swift's own `sorted` is not stable.
func stableSorted<T>(_ items: [T], by compare: (T, T) -> Int) -> [T] {
    items.enumerated()
        .sorted { a, b in
            let c = compare(a.element, b.element)
            return c != 0 ? c < 0 : a.offset < b.offset
        }
        .map(\.element)
}

/// Groups in their order, empty ones dropped; the API's order inside all but Urgent, where red
/// comes before yellow, then the longest waiting first, no `since` last.
func panel(_ rows: [SeniorRow]) -> [(group: PatientGroup, rows: [SeniorRow])] {
    let byGroup = Dictionary(
        grouping: rows.compactMap { row in groupOf(row).map { ($0, row) } }, by: \.0)
    return PatientGroup.allCases.compactMap { group in
        guard let members = byGroup[group]?.map(\.1) else { return nil }
        guard group == .urgent else { return (group, members) }
        return (
            group,
            stableSorted(members) { a, b in
                let red = (a.code == "red" ? 0 : 1) - (b.code == "red" ? 0 : 1)
                return red != 0 ? red : oldestFirst(instantOf(a.since), instantOf(b.since))
            }
        )
    }
}

/// The medic home's strip (design 2026-11-13 medic home): the codes of active seniors, and those at DAS.
struct Counts: Equatable {
    var red: Int
    var yellow: Int
    var green: Int
    var atDas: Int
}

func countsOf(_ rows: [SeniorRow]) -> Counts {
    func active(_ code: String) -> Int { rows.count { $0.state == "active" && $0.code == code } }
    return Counts(
        red: active("red"), yellow: active("yellow"), green: active("green"),
        atDas: rows.count { $0.state == "submitted" })
}

enum PatientAction: Hashable {
    case callAgain, withdraw, sign, edit
}

/// The consent text and its signature belong before the welcome call: until acceptance, signed or
/// not, so a saved signature shows „Semnat” in its place (G7, UC-01 step 5, UC-04).
func showsConsent(_ page: SeniorPage) -> Bool {
    ["draft", "submitted", "accepted"].contains(page.state)
}

/// Not yet signed, and not past acceptance (UC-04).
func signable(_ page: SeniorPage) -> Bool { showsConsent(page) && page.signedAt == nil }

/// The state in the medic's words on a card, for a state whose chip does not say it all (UC-12).
/// `wrong_number` and `unreachable` have none: their chip says it.
func says(_ state: String) -> String? { state == "accepted" ? "says_welcome_pending" : nil }

/// The actions on the medic's own patient.
func actionsFor(_ page: SeniorPage) -> [PatientAction] {
    switch page.state {
    case "draft": []
    case "wrong_number", "unreachable": [.callAgain, .edit]
    case "active": [.withdraw, .edit]
    case "submitted", "accepted": signable(page) ? [.sign, .edit] : [.edit]
    default: [.edit]
    }
}

/// One step of the enrollment; `label` is a `Localizable.xcstrings` key.
struct Stage: Equatable {
    let label: String
    let at: String?
    let reached: Bool
}

/// The enrollment's four stages and, for an end state, a fifth (03 §7). `at` is nil when the API
/// sent no date (an older API).
func stagesOf(_ page: SeniorPage) -> [Stage] {
    let reachedCount =
        switch page.state {
        case "submitted": 2
        case "accepted", "wrong_number", "unreachable", "refused": 3
        case "active", "withdrawn": 4
        default: 1  // draft, or a state this build does not know
        }
    let stages = [
        Stage(label: "stage_draft", at: page.createdAt, reached: reachedCount >= 1),
        Stage(label: "stage_submitted", at: page.submittedAt, reached: reachedCount >= 2),
        Stage(label: "stage_accepted", at: page.acceptedAt, reached: reachedCount >= 3),
        Stage(label: "stage_active", at: page.consentGivenAt, reached: reachedCount >= 4),
    ]
    let end: Stage? =
        switch page.state {
        case "refused": Stage(label: "stage_refused", at: page.consent?.at, reached: true)
        case "withdrawn": Stage(label: "stage_withdrawn", at: page.consent?.at, reached: true)
        case "wrong_number": Stage(label: "stage_wrong_number", at: nil, reached: true)
        case "unreachable": Stage(label: "stage_unreachable", at: nil, reached: true)
        default: nil
        }
    return end.map { stages + [$0] } ?? stages
}

/// The consent line's words (04 §1); a decision or method a later server adds shows raw.
let CONSENT_DECISIONS = [
    "given": "consent_given", "refused": "consent_refused", "withdrawn": "consent_withdrawn",
]

let CONSENT_METHODS = [
    "call": "consent_call", "app": "consent_app", "medic": "consent_medic", "das": "consent_das",
]

/// A stage's date, "4 nov."; with `year`, "4 nov. 2026". An unreadable date shows as sent.
func shortDate(_ iso: String, zone: TimeZone = .current, year: Bool = false) -> String {
    guard let date = instantOf(iso) else { return iso }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "ro")
    formatter.timeZone = zone
    formatter.dateFormat = year ? "d MMM yyyy" : "d MMM"
    return formatter.string(from: date)
}
