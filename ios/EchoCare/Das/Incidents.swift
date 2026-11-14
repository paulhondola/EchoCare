import Foundation

// What the DAS screens show, worked out from the API's answers (UC-11, UC-12), ported from
// android/app/.../das/Incidents.kt. Only what the medic's patient page shares with them for now:
// the relative time and a call's timeline. Task 11 adds the rest of that file.

/// How long ago something happened, as the dashboard's since(): "acum 4 min", "acum 2 h 5 min".
enum Ago: Equatable {
    case moments
    case minutes(Int)
    case hours(Int, Int)
    /// A day or more: shown as the date.
    case on(Date)
}

/// `iso` is FastAPI's UTC time, with or without fractions and an offset; nil when unreadable.
func ago(_ iso: String, now: Date) -> Ago? {
    guard let at = instant(iso) else { return nil }
    let minutes = Int(now.timeIntervalSince(at) / 60)
    // Under a minute, or a phone clock behind the server's
    if minutes < 1 { return .moments }
    if minutes < 60 { return .minutes(minutes) }
    if minutes < 24 * 60 { return .hours(minutes / 60, minutes % 60) }
    return .on(at)
}

/// One line of a call as the page shows it: what was said, or a code reported at that moment.
enum Line: Equatable {
    case said(CallTurn)
    case flagged(CallReport)

    var at: String {
        switch self {
        case .said(let turn): turn.at
        case .flagged(let report): report.at
        }
    }
}

/// Turns and reports in time order; a report at the same moment as a turn follows it.
func timeline(_ call: IncidentCall) -> [Line] {
    let lines = call.turns.map(Line.said) + call.reports.map(Line.flagged)
    return stableSorted(lines) { a, b in oldestFirst(instant(a.at), instant(b.at)) }
}
