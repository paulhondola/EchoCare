import Foundation

// The short call history on one senior's page (UC-12): what each row shows. Ported from
// android/app/.../home/Calls.kt. No transcript: the senior and a caregiver reach the calls but not
// what was said (01 §6).

/// How many calls the page lists: a short history, not the medic's full one.
let RECENT_CALLS = 5

/// The newest calls, the canceled ones left out: they never rang (03 §9).
func recentCalls(_ calls: [CallRow]) -> [CallRow] {
    Array(calls.filter { $0.state != "canceled" }.prefix(RECENT_CALLS))
}

/// A call's result as its row shows it: the code it ended with, else the state it is in.
enum Outcome: Equatable {
    case code(String)
    case state(String)
}

/// A code this build does not know shows the state instead (ADR-001 §2.3).
func outcome(_ call: CallRow) -> Outcome {
    if let code = call.finalSeverity, CODE_TONES[code] != nil { return .code(code) }
    return .state(call.state)
}

/// A call that rings or is live stands out; any other state is muted.
func stateTone(_ state: String) -> Tone {
    state == "ringing" || state == "in_progress" ? .galben : .muted
}

/// When the call ended, else when it was picked up, else when it is due; "dd.MM HH:mm" in `zone`.
func callTime(_ call: CallRow, zone: TimeZone = .current) -> String {
    let iso = call.endedAt ?? call.startedAt ?? call.dueAt
    guard let date = instant(iso) else { return iso }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = zone
    let parts = calendar.dateComponents([.day, .month, .hour, .minute], from: date)
    return String(
        format: "%02d.%02d %02d:%02d", parts.day ?? 0, parts.month ?? 0, parts.hour ?? 0,
        parts.minute ?? 0)
}

/// An ISO-8601 instant, with or without fractional seconds (the server sends both).
func instant(_ iso: String) -> Date? {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: iso) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    return formatter.date(from: iso)
}

/// The watch's chip (UC-12): a device warning when it is not watching over them (UC-13). Nil when
/// the page has no state to show, or one this build does not know (ADR-001 §2.3).
func watchChip(_ state: String?) -> (label: String, tone: Tone)? {
    switch state {
    case "ok": ("watch_ok", .muted)
    case "not_worn": ("watch_not_worn", .galben)
    case "offline": ("watch_offline", .galben)
    default: nil
    }
}

/// Whether the page shows the watch at all: unless the medic declared none (design 2026-11-14).
func showsWatch(_ senior: SeniorPage) -> Bool { senior.equipment?.contains("watch") ?? true }

/// The device warnings for a declared device that has never reported (UC-13, design 2026-11-14),
/// as string keys. None while the equipment is not stated, before DAS accepts, or for the senior
/// herself; an older API's nil `appSignedIn` warns about nothing.
func deviceWarnings(_ senior: SeniorPage, forSenior: Bool) -> [String] {
    guard let kit = senior.equipment, !forSenior, ["accepted", "active"].contains(senior.state)
    else { return [] }
    var warnings: [String] = []
    if kit.contains("watch") && senior.watchState == nil { warnings.append("device_watch_never") }
    if kit.contains("home_node") && !senior.hasRoom { warnings.append("device_node_never") }
    if kit.contains("smartphone") && senior.appSignedIn == false {
        warnings.append("device_app_never")
    }
    return warnings
}

/// The "call in progress" badge (UC-12); an older API that does not say shows none.
func showsCallBadge(_ senior: SeniorPage) -> Bool { senior.callInProgress == true }
