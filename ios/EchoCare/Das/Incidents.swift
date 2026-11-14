import Foundation

// What the DAS screens show, worked out from the API's answers (UC-11, UC-12), ported from
// android/app/.../das/Incidents.kt; IncidentsTests.swift ports IncidentsTest.kt.

/// The incident statuses the DAS app acts on (05 §1).
let OPEN = "open"
let IN_PROGRESS = "in_progress"

/// The statuses the DAS app asks for: resolved incidents are the dashboard's (04 §1).
let ACTIVE = "\(OPEN),\(IN_PROGRESS)"

/// The home's two sections, each with the longest wait first (design §"The list").
struct Sections: Equatable {
    var open: [IncidentRow]
    var inProgress: [IncidentRow]
}

/// Open by opening time, in progress by take time or else opening time, both oldest first, as the
/// dashboard's columns(). A status this build does not know is left out (ADR-001 §2.3).
func sections(_ rows: [IncidentRow]) -> Sections {
    Sections(
        open: stableSorted(rows.filter { $0.status == OPEN }) { oldestFirst(instant($0.openedAt), instant($1.openedAt)) },
        inProgress: stableSorted(rows.filter { $0.status == IN_PROGRESS }) {
            oldestFirst(instantOf($0.takenAt ?? $0.openedAt), instantOf($1.takenAt ?? $1.openedAt))
        })
}

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

/// What the senior said: the quote of the latest red report that has one, across the calls.
func seniorsWords(_ calls: [IncidentCall]) -> String? {
    let quoted = calls.flatMap(\.reports).filter {
        $0.severity == "red" && !($0.quote ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    // maxBy keeps the first of equals, as Kotlin's maxByOrNull
    var best: CallReport?
    for report in quoted where best == nil || oldestFirst(instant(report.at), instant(best!.at)) > 0 {
        best = report
    }
    return best?.quote
}

/// Newest first, the newest being the one shown open. GET /incidents/{id} sends the calls oldest
/// first (by creation, then attempt); their start time cannot order them, since an unanswered or
/// queued call never started.
func newestFirst(_ calls: [IncidentCall]) -> [IncidentCall] { calls.reversed() }

/// Whether `callId` shows its transcript: as the dispatcher `toggled` it, else open only when it is
/// the newest, so a call that joins the incident while the page is open opens itself.
func expanded(_ callId: String, newestId: String, toggled: [String: Bool]) -> Bool {
    toggled[callId] ?? (callId == newestId)
}

/// The "Apel în curs" badge (UC-12): a call ringing or live.
func callLive(_ calls: [IncidentCall]) -> Bool {
    calls.contains { $0.state == "ringing" || $0.state == "in_progress" }
}

/// The event's place as the page shows it; `accuracy` in whole metres, nil when unknown.
struct Location: Equatable {
    var latitude: String
    var longitude: String
    var accuracy: Int?
}

/// Nil without coordinates. An unknown accuracy is left out, never shown as ±0 m.
func location(_ event: TriggerEvent) -> Location? {
    guard let lat = event.latitude, let lng = event.longitude else { return nil }
    // Five decimals, as the dashboard's toFixed(5): about a metre
    return Location(
        latitude: String(format: "%.5f", lat), longitude: String(format: "%.5f", lng),
        accuracy: event.accuracy.map { Int($0.rounded()) })
}

/// Seniors have no city field; the service is DAS Timișoara (design §"Phone and Maps").
let CITY = "Timișoara"

/// "Deschide în Hărți": an Apple Maps link to the event's location when it has one, else to the
/// street address. Nil when there is neither, so the button is not shown. Android's is a `geo:`
/// URI, which iOS does not open.
func mapsUrl(_ senior: IncidentSenior, _ event: TriggerEvent?) -> String? {
    if let lat = event?.latitude, let lng = event?.longitude {
        return "https://maps.apple.com/?ll=\(lat),\(lng)&q=\(lat),\(lng)"
    }
    guard let street = senior.street, !street.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
    let place = ([street] + [senior.streetNumber].compactMap { $0 }).joined(separator: " ") + ", \(CITY)"
    let unreserved = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    return "https://maps.apple.com/?q=" + (place.addingPercentEncoding(withAllowedCharacters: unreserved) ?? "")
}

/// The colour of a status's chip and card bar, as the dashboard's: red open, yellow in progress,
/// green resolved. A status this build does not know is muted.
func statusTone(_ status: String) -> Tone {
    switch status {
    case OPEN: .rosu
    case IN_PROGRESS: .galben
    case "resolved": .verde
    default: .muted
    }
}

/// The one action the pinned bar offers (UC-11 steps 2 and 4).
enum Act { case take, resolve }

/// Preiau while open, Rezolvă cazul while in progress for any DAS employee, else nothing.
func actFor(_ status: String) -> Act? {
    switch status {
    case OPEN: .take
    case IN_PROGRESS: .resolve
    default: nil
    }
}

/// One line over the pinned bar after a refused Preiau or Trimite (the enrollment form has its own
/// `Notice`).
enum DasNotice: Equatable {
    /// "Preluat deja de {name}."
    case takenBy(String)
    /// A `Localizable.xcstrings` key.
    case says(String)
    /// Signed out or no longer registered: sign-in replaces the screen.
    case ends(Failure)
}

/// What a refused `act` tells the dispatcher, in the dashboard's words (commands.ts).
func noticeAfter(_ refusal: Refusal, act: Act) -> DasNotice {
    switch refusal {
    case .alreadyDone(let name):
        if act == .resolve { .says("already_resolved") } else if let name { .takenBy(name) } else { .says("incident_changed") }
    case .wrongState: .says("incident_changed")
    case .failed(let failure):
        switch failure {
        case .notAllowed: .says("not_allowed_action")
        case .notFound: .says("incident_gone")
        case .signedOut, .notRegistered: .ends(failure)
        case .noConnection: .says("send_failed")
        }
    // The form checks what the server would refuse; anything else is a failed send
    case .invalid, .incomplete, .phoneTaken: .says("send_failed")
    }
}

/// The resolve note's limit (04 §2).
let NOTE_MAX = 1000

/// Trimite needs an outcome and a note of 1 to `NOTE_MAX` characters (04 §2).
func canSend(_ outcome: String?, _ note: String) -> Bool {
    outcome != nil && !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && note.count <= NOTE_MAX
}

/// The five outcomes of 04 §2, in the dashboard's order and words (`label` is a string key).
let OUTCOMES: [(value: String, label: String)] = [
    ("senior_ok", "outcome_senior_ok"), ("team_sent", "outcome_team_sent"),
    ("called_112", "outcome_called_112"), ("not_reached", "outcome_not_reached"),
    ("false_alarm", "outcome_false_alarm"),
]
