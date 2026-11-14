import SwiftUI

/// „Pacient nou”: the medic's four steps (seniors §9), ported from
/// android/app/.../enroll/EnrollScreen.kt. Full screen on an iPhone and an iPad (SE20).
/// `onSubmitted` returns to the home, `onDone` to the senior's page, `onLeave` closes the form.
struct EnrollView: View {
    let onLeave: () -> Void
    let onSubmitted: () -> Void
    let onDone: (String) -> Void
    let onSessionEnd: (Failure) -> Void

    @State private var model: EnrollModel
    @State private var started = false

    init(
        seniorId: String?, api: ApiClient = ApiClient(tokens: FirebaseTokenSource()),
        onLeave: @escaping () -> Void, onSubmitted: @escaping () -> Void,
        onDone: @escaping (String) -> Void, onSessionEnd: @escaping (Failure) -> Void
    ) {
        self.onLeave = onLeave
        self.onSubmitted = onSubmitted
        self.onDone = onDone
        self.onSessionEnd = onSessionEnd
        _model = State(initialValue: EnrollModel(seniorId: seniorId, api: api))
    }

    var body: some View {
        let title = model.existing ? model.saved[.formOfAddress] : nil
        Frame(
            title.flatMap { $0.trimmed.isEmpty ? nil : $0 } ?? String(localized: "new_patient"),
            onBack: { if !model.back() { onLeave() } }
        ) {
            LoadBody(load: model.form, onRetry: { Task { await model.open() } }, onSessionEnd: onSessionEnd) { _ in
                Steps(model: model, onDone: onDone, onSessionEnd: onSessionEnd)
            }
        }
        .task {
            // Once: the task starts again when the view reappears
            guard !started else { return }
            started = true
            await model.open()
        }
        .onChange(of: model.submitted) { _, submitted in if submitted { onSubmitted() } }
        // No profile from a form: switching role there would drop what was typed
        .environment(\.openProfile, nil)
    }
}

/// One column, at most 600pt wide and centred on an iPad, full width on an iPhone (seniors §9.4).
private struct Steps: View {
    let model: EnrollModel
    let onDone: (String) -> Void
    let onSessionEnd: (Failure) -> Void

    @State private var wide = false
    /// A stroke is being drawn on the pad: the page holds still.
    @State private var drawing = false

    var body: some View {
        ScrollViewReader { scroll in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    StepHeader(step: model.step, wide: wide).id("top")
                    switch model.step {
                    case .senior, .address:
                        Fields(model: model, fields: model.step.fields, values: model.values)
                    case .caregivers: CaregiversStep(model: model)
                    case .review: ReviewStep(model: model, drawing: $drawing, onSessionEnd: onSessionEnd)
                    }
                    if let notice = model.notice { NoticeLine(notice: notice) }
                    Buttons(model: model, onDone: onDone)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 20)
                .frame(maxWidth: 600)
                .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .scrollDisabled(drawing)
            .onChange(of: model.step) { scroll.scrollTo("top", anchor: .top) }
        }
        .onGeometryChange(for: Bool.self) { $0.size.width >= 600 } action: { wide = $0 }
    }
}

/// „Pasul 2 din 4” and the step's name; on a wide screen, all four with this one marked.
private struct StepHeader: View {
    let step: Step
    let wide: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionLabel(verbatim: localized("step_counter", step.rawValue + 1, Step.allCases.count))
            if wide {
                WrappingRow(spacing: 20, lineSpacing: 10) {
                    ForEach(Step.allCases, id: \.self) { StepName(step: $0, current: $0 == step) }
                }
            } else {
                Text(LocalizedStringKey(step.title)).textStyle(Theme.titleLarge).foregroundStyle(Theme.fg)
                    .accessibilityAddTraits(.isHeader)
            }
            Rule()
        }
    }
}

private struct StepName: View {
    let step: Step
    let current: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(LocalizedStringKey(step.title)).textStyle(Theme.titleMedium)
                .foregroundStyle(current ? Theme.fg : Theme.fgMuted)
            Rectangle().fill(current ? Theme.link : Theme.canvas).frame(height: 2)
        }
        // As wide as the name, as Android's IntrinsicSize.Max: the bar must not ask for the row
        .fixedSize(horizontal: true, vertical: false)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(current ? [.isHeader, .isSelected] : [])
    }
}

/// Text fields. A field over its limit says so; the server's refusals say the rest (§9.3).
private struct Fields: View {
    let model: EnrollModel
    let fields: [Field]
    let values: [Field: String]

    var body: some View {
        let problems = problems(values, fields, draft: model.isDraft)
        ForEach(fields, id: \.self) { field in
            SnTextField(
                text: Binding(get: { values[field] ?? "" }, set: { model.type(field, $0) }),
                label: LocalizedStringKey(field.label),
                keyboard: field.isPhone ? .phonePad : .default,
                mono: field.isPhone,
                hint: field == .formOfAddress ? "form_of_address_hint" : nil,
                error: model.errors[field].map { String(localized: String.LocalizationValue($0)) }
                    ?? (problems[field] == .tooLong ? localized("too_long", field.max ?? 0) : nil),
                capitalization: capitalization(field))
        }
    }

    private func capitalization(_ field: Field) -> TextInputAutocapitalization {
        switch field {
        case .fullName, .caregiverName: .words
        case .street, .keyHolder, .landmark: .sentences
        default: .never
        }
    }
}

/// Step 3: the caregivers so far, and a row to add one. Each button calls the API at once.
private struct CaregiversStep: View {
    let model: EnrollModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if model.caregivers.isEmpty {
                Text("no_caregivers").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgMuted)
                    .padding(.vertical, 12)
            }
            ForEach(model.caregivers.indices, id: \.self) { i in
                let caregiver = model.caregivers[i]
                CaregiverRow(caregiver: caregiver, enabled: !model.busy) {
                    Task { await model.remove(caregiver) }
                }
                Rule(strong: i == model.caregivers.count - 1)
            }
        }
        Text("new_caregiver").textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
            .accessibilityAddTraits(.isHeader)
        Fields(model: model, fields: Step.caregivers.fields, values: model.adding)
        SnButton("add", kind: .link) { Task { await model.add() } }
            .disabled(model.busy || !problems(model.adding, Step.caregivers.fields, draft: model.isDraft).isEmpty)
    }
}

private struct CaregiverRow: View {
    let caregiver: Caregiver
    let enabled: Bool
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: [caregiver.displayName, caregiver.relation].compactMap { $0 }.joined(separator: " · "))
                    .textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                Text(verbatim: formatPhone(caregiver.phone)).textStyle(Theme.mono).foregroundStyle(Theme.fgSoft)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            SnButton("remove", kind: .outline, action: onRemove).disabled(!enabled)
        }
        .padding(.vertical, 12)
    }
}

/// Step 4: the senior as GET seniors/{id} has them, and what submitting still needs.
private struct ReviewStep: View {
    let model: EnrollModel
    let drawing: Binding<Bool>
    let onSessionEnd: (Failure) -> Void

    var body: some View {
        LoadBody(load: model.review, onRetry: { Task { await model.reread() } }, onSessionEnd: onSessionEnd) { senior in
            VStack(alignment: .leading, spacing: 16) {
                // A refused submit names what is missing itself, over the buttons
                let missing = missingOf(senior)
                if senior.state == "draft", !missing.isEmpty, !model.noticeIsMissing {
                    NoticeLine(notice: .missing(missing))
                }
                SeniorDetails(senior: senior, callSenior: false, calls: false)
                MedicalUpload(model: model)
                if showsConsent(senior) {
                    ConsentSection(signedAt: senior.signedAt, busy: model.busy, drawing: drawing) { form in
                        Task { await model.sign(form) }
                    }
                }
            }
        }
    }
}

/// The optional PDF (design §5.7): analysed once DAS accepts the patient.
private struct MedicalUpload: View {
    let model: EnrollModel

    @State private var picking = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionLabel("medical_section")
            if model.medicalSent {
                Text("medical_waiting").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgSoft)
            }
            if let line = model.medicalNotice {
                Text(LocalizedStringKey(line)).textStyle(Theme.bodyLarge).foregroundStyle(Theme.galbenFg)
            }
            SnButton(model.medicalSent ? "medical_replace" : "medical_upload", kind: .outline) { picking = true }
                .disabled(model.uploading)
        }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.pdf]) { result in
            switch result {
            case .success(let url): Task { await model.uploadPdf(readPdf(url)) }
            case .failure(let error):
                // Closing the picker is not a failure
                if (error as? CocoaError)?.code != .userCancelled { Task { await model.uploadPdf(nil) } }
            }
        }
    }
}

private struct NoticeLine: View {
    let notice: Notice

    var body: some View {
        let text =
            switch notice {
            case .says(let key): String(localized: String.LocalizationValue(key))
            case .missing(let names):
                localized("missing", names.map { labelOf($0, in: MISSING_LABELS) }.joined(separator: ", "))
            }
        Text(verbatim: text).textStyle(Theme.bodyLarge).foregroundStyle(Theme.galbenFg)
            .frame(maxWidth: .infinity, alignment: .leading)
            .onAppear { AccessibilityNotification.Announcement(text).post() }
    }
}

/// „Înapoi” from step 2 on, then „Continuă”, or on step 4 „Trimite la DAS” or „Gata”.
private struct Buttons: View {
    let model: EnrollModel
    let onDone: (String) -> Void

    var body: some View {
        WrappingRow(spacing: 8, lineSpacing: 8) {
            if model.step != .senior {
                SnButton("back", kind: .outline) { _ = model.back() }.disabled(model.busy)
            }
            if model.step != .review {
                SnButton("next_step", kind: .link) { Task { await model.next() } }
                    .disabled(model.busy || !canContinue(model.step, model.values, draft: model.isDraft))
            } else if case .ready(let senior, _) = model.review {
                if senior.state == "draft" {
                    SnButton("submit", kind: .success) { Task { await model.submit() } }
                        .disabled(
                            model.busy || model.uploading || !missingOf(senior).isEmpty || model.noticeIsMissing)
                } else {
                    SnButton("done", kind: .link) { onDone(senior.id) }
                }
            }
        }
    }
}
