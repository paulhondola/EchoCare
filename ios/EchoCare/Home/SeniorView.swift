import SwiftUI

/// The senior's home: everything GET /seniors/{id} returns for them (seniors SE7), „Sunați-mă”, the
/// mock call card and „Pornește monitorizarea”. Ported from the own-home half of android/app's
/// home/SeniorScreen.kt `PatientPane`. Her phone relays the watch (G5), so the page keeps it
/// reading; Android's `BackgroundPrompt` has no iOS counterpart, as the relay is Task 8's.
struct SeniorHome: View {
    let onSessionEnd: (Failure) -> Void

    @State private var model = SeniorModel()

    var body: some View {
        SeniorView(model: model, onSessionEnd: onSessionEnd)
    }
}

struct SeniorView: View {
    let model: SeniorModel
    let onSessionEnd: (Failure) -> Void

    var body: some View {
        // Her form of address once loaded, the app's name before
        let title =
            if case .ready(let senior, _) = model.page { senior.formOfAddress } else { String(localized: "app_name") }
        Frame(title) {
            LoadBody(
                load: model.page,
                onRetry: { Task { await model.load() } },
                onSessionEnd: onSessionEnd
            ) { senior in
                VStack(spacing: 0) {
                    if model.warning { Banner("warning_active", tone: .galben) }
                    ScrollView {
                        VStack(alignment: .leading, spacing: 0) {
                            // Asks for a wellbeing call (UC-10)
                            CallMeButton(state: model.callMe, action: model.requestCall)
                            // A call to answer here instead of on the phone (design §6.2)
                            if let call = model.mock {
                                MockCallCard(call: call) { answer in Task { await model.answerMock(answer) } }
                            }
                            MonitoringButton(state: model.monitoring) { Task { await model.startMonitoring() } }
                            SeniorDetails(senior: senior, callSenior: false)
                            if let calls = model.calls { CallList(calls: recentCalls(calls)) }
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 20)
                        .frame(maxWidth: 600)
                        .frame(maxWidth: .infinity)
                    }
                }
            }
        }
        .reread { await model.load() }
    }
}

/// „Pornește monitorizarea”: starts the watch's monitoring from the phone (design, Monitoring).
private struct MonitoringButton: View {
    let state: Monitoring
    let action: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            switch state {
            case .started: Banner("monitoring_started", tone: .verde)
            case .failed: Banner("monitoring_failed", tone: .rosu)
            default: EmptyView()
            }
            SnButton("monitoring_start", kind: .outline, fullWidth: true, minHeight: 56, action: action)
                .disabled(state == .starting)
        }
        .padding(.bottom, 16)
    }
}

/// One senior, laid out like the dashboard's dossier: labelled rows, 1pt between rows, 2pt under a
/// group. `callSenior` is false on the senior's own page, since they do not need a button to call
/// themselves; `calls` false hides every call button. `below` goes under the name, over the rule:
/// the medic's stages, consent and actions.
struct SeniorDetails<Below: View>: View {
    let senior: SeniorPage
    let callSenior: Bool
    var calls = true
    let below: Below?

    init(senior: SeniorPage, callSenior: Bool, calls: Bool = true, @ViewBuilder below: () -> Below) {
        self.senior = senior
        self.callSenior = callSenior
        self.calls = calls
        self.below = below()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 10) {
                Text(verbatim: senior.fullName).textStyle(Theme.headlineSmall).foregroundStyle(Theme.fg)
                StateLabel(state: senior.state)
                CodeLabel(code: senior.code, reason: senior.reason)
                if showsCallBadge(senior) { Chip("call_live", tone: .galben) }
                if let chip = watchChip(senior.watchState) {
                    if senior.watchState == "ok", let pulse = senior.lastPulse {
                        Chip(verbatim: localized("watch_ok_pulse", pulse), tone: chip.tone)
                    } else {
                        Chip(LocalizedStringKey(chip.label), tone: chip.tone)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.bottom, 16)
            if let below {
                below
                Rule().padding(.top, 16)
            } else {
                Rule()
            }

            Group {
                if calls && callSenior {
                    FieldRow("label_phone", action: { CallButton(e164: senior.phone) }) {
                        PhoneNumber(e164: senior.phone, landline: senior.landline)
                    }
                } else {
                    FieldRow("label_phone") { PhoneNumber(e164: senior.phone, landline: senior.landline) }
                }
                FieldRow("label_address") {
                    Value(
                        text: place(
                            street: senior.street, streetNumber: senior.streetNumber, block: senior.block,
                            staircase: senior.staircase, floor: senior.floor, apartment: senior.apartment))
                }
                if let code = senior.intercomCode {
                    FieldRow("label_intercom") {
                        Text(verbatim: code).textStyle(Theme.mono).foregroundStyle(Theme.fg)
                    }
                }
                if let holder = senior.keyHolder { FieldRow("label_key_holder") { Value(text: holder) } }
                if let landmark = senior.landmark { FieldRow("label_landmark") { Value(text: landmark) } }
                if let window = senior.callWindow { FieldRow("section_call_window") { Value(text: window) } }
                FieldRow("role_medic", last: true) {
                    Value(text: [senior.medic.displayName, senior.medic.practice].compactMap { $0 }.joined(separator: " · "))
                }
            }

            SectionLabel("section_caregivers").padding(.top, 20).padding(.bottom, 4)
            if senior.caregivers.isEmpty {
                Text("no_caregivers").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgMuted)
                    .padding(.vertical, 12)
            }
            ForEach(Array(senior.caregivers.enumerated()), id: \.offset) { i, caregiver in
                VStack(spacing: 0) {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: [caregiver.displayName, caregiver.relation].compactMap { $0 }.joined(separator: " · "))
                                .textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                            Text(verbatim: formatPhone(caregiver.phone)).textStyle(Theme.mono).foregroundStyle(Theme.fgSoft)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        if calls { CallButton(e164: caregiver.phone) }
                    }
                    .padding(.vertical, 12)
                    Rule(strong: i == senior.caregivers.count - 1)
                }
            }
        }
    }

}

extension SeniorDetails where Below == EmptyView {
    init(senior: SeniorPage, callSenior: Bool, calls: Bool = true) {
        self.senior = senior
        self.callSenior = callSenior
        self.calls = calls
        self.below = nil
    }
}

/// The street with block, staircase, floor and apartment (G13), from what was filled in. The
/// senior's page and the DAS incident page both show it.
func place(
    street: String?, streetNumber: String?, block: String?, staircase: String?, floor: String?,
    apartment: String?
) -> String {
    func part(_ key: String, _ value: String?) -> String? { value.map { localized(key, $0) } }
    let line = [street, streetNumber].compactMap { $0 }.joined(separator: " ")
    let parts = [
        line.trimmingCharacters(in: .whitespaces).isEmpty ? nil : line,
        part("address_block", block),
        part("address_staircase", staircase),
        part("address_floor", floor),
        part("address_apartment", apartment),
    ].compactMap { $0 }
    return parts.isEmpty ? String(localized: "no_address") : parts.joined(separator: ", ")
}

private struct Value: View {
    let text: String

    var body: some View {
        Text(verbatim: text).textStyle(Theme.bodyLarge).foregroundStyle(Theme.fg)
    }
}

/// The enrollment state as a tinted chip; nothing for a state this build does not know.
struct StateLabel: View {
    let state: String

    var body: some View {
        if let label = STATE_LABELS[state] { Chip(LocalizedStringKey(label), tone: STATE_TONES[state] ?? .muted) }
    }
}

/// The code as a tinted chip with its reason; nothing for a code this build does not know (Q17).
struct CodeLabel: View {
    let code: String?
    let reason: String?

    var body: some View {
        if let code, let label = CODE_LABELS[code] {
            HStack(spacing: 8) {
                Chip(LocalizedStringKey(label), tone: CODE_TONES[code] ?? .muted)
                if let reason { Text(verbatim: reason).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgMuted) }
            }
        }
    }
}

/// The medic's „Transcriere” on each call: what was read, and how to read one (04 §1).
struct Transcripts {
    let read: [String: Load<IncidentCall>]
    let open: (String) -> Void
}

/// „Apeluri recente” or, for the medic, „Apeluri”: when, what started it, and the code it ended
/// with or its state (UC-12). With `transcripts`, each row opens what was said under it.
struct CallList: View {
    let calls: [CallRow]
    var title = "section_recent_calls"
    var transcripts: Transcripts?

    /// The rows the medic unfolded; „Ascunde” folds one, and the transcript stays read
    @State private var shown: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionLabel(LocalizedStringKey(title)).padding(.top, 20).padding(.bottom, 4)
            if calls.isEmpty {
                Text("no_recent_calls").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgMuted)
                    .padding(.vertical, 12)
            }
            ForEach(Array(calls.enumerated()), id: \.element.id) { i, call in
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(verbatim: line(call)).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                            if let reason = call.reason {
                                Text(verbatim: reason).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgMuted)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        switch outcome(call) {
                        case .code(let code):
                            Chip(verbatim: labelOf(code, in: CODE_LABELS), tone: CODE_TONES[code] ?? .muted)
                        case .state(let state):
                            Chip(verbatim: labelOf(state, in: CALL_STATE_LABELS), tone: stateTone(state))
                        }
                    }
                    .padding(.vertical, 12)
                    if let transcripts {
                        let open = shown.contains(call.id)
                        SnButton(open ? "hide" : "transcript", kind: .link) {
                            if open {
                                shown.remove(call.id)
                            } else {
                                shown.insert(call.id)
                                transcripts.open(call.id)
                            }
                        }
                        .padding(.bottom, 12)
                        if open, let read = transcripts.read[call.id] { TranscriptOf(read: read) }
                    }
                    Rule(strong: i == calls.count - 1)
                }
            }
        }
    }

    private func line(_ call: CallRow) -> String {
        localized("recent_call_line", callTime(call), labelOf(call.trigger, in: TRIGGER_LABELS))
    }
}
