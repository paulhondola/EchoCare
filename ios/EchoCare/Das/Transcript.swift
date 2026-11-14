import SwiftUI

// A call's transcript and the relative time, as the DAS incident page shows them, ported from
// android/app's das/IncidentScreen.kt `Transcript` and das/IncidentsScreen.kt `agoText`. The
// medic's patient page shows them too (UC-12); Task 11's incident page reuses this file.

/// "acum 4 min", "acum 2 h 5 min"; a day or more as the date and time in the phone's zone.
func agoText(_ ago: Ago, zone: TimeZone = .current) -> String {
    switch ago {
    case .moments: return String(localized: "ago_moments")
    case .minutes(let m): return localized("ago_minutes", m)
    case .hours(let h, let m): return localized("ago_hours", h, m)
    case .on(let at):
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "ro")
        formatter.timeZone = zone
        formatter.dateFormat = "dd.MM.yyyy HH:mm"
        return formatter.string(from: at)
    }
}

/// `iso` as "HH:mm:ss" in the phone's zone (the API sends UTC); an unreadable time as it came.
func clockTime(_ iso: String, zone: TimeZone = .current) -> String {
    guard let date = instant(iso) else { return iso }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "ro")
    formatter.timeZone = zone
    formatter.dateFormat = "HH:mm:ss"
    return formatter.string(from: date)
}

/// A call's turns and reported codes in time order, then whether the hand-over was answered.
struct Transcript: View {
    let call: IncidentCall

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(timeline(call).enumerated()), id: \.offset) { _, line in
                switch line {
                case .said(let turn): Said(turn: turn)
                case .flagged(let report): Flagged(report: report)
                }
            }
            if let answered = call.handoverAnswered {
                Text(answered ? "handover_call_yes" : "handover_call_no")
                    .textStyle(Theme.labelLarge)
                    .foregroundStyle(answered ? Theme.verdeFg : Theme.rosuFg)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct Said: View {
    let turn: CallTurn

    var body: some View {
        let (who, color): (LocalizedStringKey, Color) =
            switch turn.speaker {
            case "senior": ("speaker_senior", Theme.fgMuted)
            case "agent": ("speaker_agent", Theme.link)
            case "das": ("speaker_das", Theme.fg)
            default: ("speaker_system", Theme.fgMuted)
            }
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                Text(who).textCase(.uppercase).textStyle(Theme.labelSmall).foregroundStyle(color)
                Text(verbatim: clockTime(turn.at)).textStyle(Theme.mono).foregroundStyle(
                    Theme.fgMuted)
            }
            Text(
                verbatim: turn.kind == "keys" ? localized("turn_keys", turn.content) : turn.content
            )
            .textStyle(Theme.bodyMedium)
            .foregroundStyle(Theme.fg)
            .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct Flagged: View {
    let report: CallReport

    var body: some View {
        let tone = CODE_TONES[report.severity] ?? .muted
        Text(
            verbatim: localized("flagged", labelOf(report.severity, in: CODE_LABELS), report.reason)
        )
        .textStyle(Theme.bodySmall)
        .foregroundStyle(tone.text)
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tone.fill)
    }
}
