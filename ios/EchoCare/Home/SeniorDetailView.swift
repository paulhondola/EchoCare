import SwiftUI

/// One senior's page opened from a list: everything GET /seniors/{id} returns, the same for every
/// role (seniors SE7). Ported from android/app's home/SeniorScreen.kt `SeniorScreen` with an id.
/// `onEdit` is the medic's: it opens her form and adds her panel (UC-12).
struct SeniorPageView: View {
    let id: String
    let onBack: () -> Void
    let onSessionEnd: (Failure) -> Void
    var onEdit: ((String) -> Void)?

    @State private var model: SeniorDetailModel

    init(
        id: String, onBack: @escaping () -> Void, onSessionEnd: @escaping (Failure) -> Void,
        onEdit: ((String) -> Void)? = nil, api: ApiClient = ApiClient(tokens: FirebaseTokenSource())
    ) {
        self.id = id
        self.onBack = onBack
        self.onSessionEnd = onSessionEnd
        self.onEdit = onEdit
        _model = State(initialValue: SeniorDetailModel(api: api))
    }

    var body: some View {
        let title =
            if case .ready(let senior, _) = model.page { senior.formOfAddress } else {
                String(localized: "app_name")
            }
        Frame(title, onBack: onBack) {
            PatientPane(id: id, model: model, onSessionEnd: onSessionEnd, onEdit: onEdit)
        }
    }
}

/// One senior's page without its frame: the body the page and Monitorizare's right pane share, so
/// a change to it is made once (UC-12). `onEdit` is given to the medic only: with it the page adds
/// her patient's stages, consent, every call with its transcript, the actions of her panel and the
/// medical record (UC-04, UC-12, design §5.7). `onChanged` runs after a command the server
/// answered, so Monitorizare's list beside the pane moves the patient at once.
struct PatientPane: View {
    let id: String
    let model: SeniorDetailModel
    let onSessionEnd: (Failure) -> Void
    var onEdit: ((String) -> Void)?
    var onChanged: () async -> Void = {}

    // „Retragere consimțământ” asks first; „Semnătură” opens the consent text under the actions
    @State private var withdrawing = false
    @State private var signing = false
    /// A stroke is being drawn on the pad: the page holds still.
    @State private var drawing = false

    var body: some View {
        LoadBody(load: model.page, onRetry: { Task { await load() } }, onSessionEnd: onSessionEnd) {
            senior in
            // An alert can open a senior she only cares for: her panel is for her own patients
            let medic = onEdit != nil && !model.notHers
            VStack(spacing: 0) {
                if medic {
                    CommandBanners(notice: model.notice, numberChanged: model.numberChanged)
                }
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        if medic {
                            SeniorDetails(senior: senior, callSenior: true) { panel(senior) }
                        } else {
                            SeniorDetails(senior: senior, callSenior: true)
                        }
                        // The medic sees every call and what was said; a caregiver a short list (01 §6)
                        if let calls = model.calls {
                            if medic {
                                CallList(
                                    calls: calls, title: "section_calls",
                                    transcripts: Transcripts(read: model.transcripts) { callId in
                                        Task { await model.openTranscript(callId: callId) }
                                    })
                            } else {
                                CallList(calls: recentCalls(calls))
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 20)
                    .frame(maxWidth: 600)
                    .frame(maxWidth: .infinity)
                }
                .scrollDisabled(drawing)
            }
            .alert(
                Text(verbatim: localized("withdraw_title", senior.formOfAddress)),
                isPresented: $withdrawing
            ) {
                Button(role: .destructive) {
                    Task { await model.withdraw(id: senior.id, onChanged: onChanged) }
                } label: {
                    Text("withdraw_confirm")
                }
                Button(role: .cancel) {
                } label: {
                    Text("cancel")
                }
            } message: {
                Text("withdraw_text")
            }
        }
        .reread { await load() }
        .task(id: id) { if onEdit != nil { await model.checkHers(id: id) } }
    }

    private func load() async {
        // The medic's panel reads the medical record with the page (design §5.7)
        await model.load(id: id, medical: onEdit != nil)
    }

    @ViewBuilder private func panel(_ senior: SeniorPage) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Stages(stages: stagesOf(senior))
            ConsentLine(senior: senior)
            Actions(actions: actionsFor(senior), busy: model.busy) { action in
                switch action {
                // At once, no confirmation (UC-04)
                case .callAgain: Task { await model.callAgain(id: senior.id, onChanged: onChanged) }
                case .withdraw: withdrawing = true
                case .sign: signing.toggle()
                case .edit:
                    model.editing()
                    onEdit?(senior.id)
                }
            }
            // Stays open after the save, showing „Semnat” with the date (G7)
            if signing && showsConsent(senior) {
                ConsentSection(signedAt: senior.signedAt, busy: model.busy, drawing: $drawing) {
                    form in
                    Task { await model.sign(id: senior.id, form: form, onChanged: onChanged) }
                }
                .padding(.top, 16)
            }
            MedicalSection(
                record: model.medical, seniorState: senior.state, busy: model.busy,
                uploadNotice: model.uploadNotice,
                onUpload: { pdf in
                    Task { await model.uploadPdf(id: senior.id, pdf: pdf, onChanged: onChanged) }
                },
                onConfirm: { items in
                    Task { await model.confirmMedical(id: senior.id, items: items) }
                },
                onReanalyze: { Task { await model.reanalyzeMedical(id: senior.id) } })
        }
    }
}

/// The banners after a command and after a new number (UC-12, 04 §2).
private struct CommandBanners: View {
    let notice: CommandOutcome?
    let numberChanged: Bool

    var body: some View {
        switch notice {
        case .refused(let reason):
            let key =
                switch reason {
                case nil: "not_allowed_action"
                case "not_found": "not_found"
                case "invalid": "not_accepted"
                default: "changed_state"
                }
            Banner(key, tone: .galben)
        case .offline: Banner("offline_retry", tone: .galben)
        case .done, nil: EmptyView()
        }
        if numberChanged { Banner("number_changed", tone: .link) }
    }
}

/// The enrollment's stages under the name: lit up to where the senior is (03 §7, UC-04).
private struct Stages: View {
    let stages: [Stage]

    var body: some View {
        HStack(alignment: .top, spacing: 4) {
            ForEach(Array(stages.enumerated()), id: \.offset) { _, stage in
                VStack(alignment: .leading, spacing: 2) {
                    Text(LocalizedStringKey(stage.label))
                        .textStyle(Theme.labelMedium)
                        .foregroundStyle(stage.reached ? Theme.fg : Theme.fgSubtle)
                        .fixedSize(horizontal: false, vertical: true)
                    if let at = stage.at {
                        Text(verbatim: shortDate(at))
                            .textStyle(Theme.labelSmall)
                            .foregroundStyle(stage.reached ? Theme.fgMuted : Theme.fgSubtle)
                    }
                }
                .padding(.top, 9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .overlay(alignment: .top) {
                    Rectangle().fill(stage.reached ? Theme.verde : Theme.line).frame(height: 3)
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// „Dat · la apel · 4 nov. 2026” and „Semnat pe tabletă · …”; neither, no line (04 §1, G7).
private struct ConsentLine: View {
    let senior: SeniorPage

    var body: some View {
        let lines = [
            senior.consent.map {
                localized(
                    "consent_line", labelOf($0.decision, in: CONSENT_DECISIONS),
                    labelOf($0.method, in: CONSENT_METHODS),
                    shortDate($0.at, year: true))
            },
            senior.signedAt.map { localized("signed_on_tablet", shortDate($0, year: true)) },
        ].compactMap { $0 }
        if !lines.isEmpty {
            HStack(alignment: .top, spacing: 12) {
                SectionLabel("consent_label").frame(width: 112, alignment: .leading)
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(lines, id: \.self) { line in
                        Text(verbatim: line).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fg)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.top, 16)
        }
    }
}

/// The actions of the senior's state, all in sight (UC-12, design "The patient").
private struct Actions: View {
    let actions: [PatientAction]
    let busy: Bool
    let onAction: (PatientAction) -> Void

    var body: some View {
        if !actions.isEmpty {
            WrappingRow(spacing: 8, lineSpacing: 8) {
                ForEach(actions, id: \.self) { action in
                    switch action {
                    case .callAgain:
                        SnButton("call_again", kind: .success) { onAction(action) }.disabled(busy)
                    case .withdraw:
                        SnButton("withdraw", kind: .danger) { onAction(action) }.disabled(busy)
                    case .sign:
                        SnButton("sign") { onAction(action) }
                    case .edit:
                        SnButton("edit_data") { onAction(action) }
                    }
                }
            }
            .padding(.top, 16)
        }
    }
}

/// One call's transcript under its row, as on the DAS incident page (UC-12).
struct TranscriptOf: View {
    let read: Load<IncidentCall>

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            switch read {
            case .loading:
                ProgressView().tint(Theme.fgMuted)
            case .ready(let call, _):
                if call.turns.isEmpty && call.reports.isEmpty && call.answers.isEmpty {
                    Text("no_transcript").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgMuted)
                } else {
                    Transcript(call: call)
                    Answers(answers: call.answers)
                }
            // „Transcriere” again reads it again
            case .failed(let failure):
                let key =
                    switch failure {
                    case .notFound: "not_found"
                    case .notAllowed: "not_allowed"
                    default: "no_connection"
                    }
                Text(LocalizedStringKey(key)).textStyle(Theme.bodyLarge).foregroundStyle(
                    Theme.fgMuted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Theme.subtle)
        .padding(.bottom, 12)
    }
}

/// What the call heard, under its transcript, one line per answer (04 §1):
/// Stare: rău · neclar · „Rău”.
private struct Answers: View {
    let answers: [CallAnswer]

    var body: some View {
        if !answers.isEmpty {
            SectionLabel("answers").padding(.top, 4)
            ForEach(Array(answers.enumerated()), id: \.offset) { _, answer in
                Text(verbatim: Self.line(answer)).textStyle(Theme.bodyMedium).foregroundStyle(
                    Theme.fg)
            }
        }
    }

    static func line(_ answer: CallAnswer) -> String {
        let quote = answer.quote.trimmingCharacters(in: .whitespaces)
        return [
            "\(labelOf(answer.field, in: ANSWER_FIELDS)): \(labelOf(answer.value, in: ANSWER_VALUES))",
            answer.clear ? nil : String(localized: "answer_unclear"),
            quote.isEmpty ? nil : localized("answer_quote", answer.quote),
        ].compactMap { $0 }.joined(separator: " · ")
    }
}
