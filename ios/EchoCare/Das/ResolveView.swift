import SwiftUI

/// „Rezolvare caz”: one of five outcomes and a short note (UC-11 step 4, 04 §2), ported from
/// android/app's das/ResolveScreen.kt.
struct ResolveView: View {
    let onBack: () -> Void
    let onDone: () -> Void
    let onSessionEnd: (Failure) -> Void

    @State private var model: ResolveModel

    init(
        id: String, onBack: @escaping () -> Void, onDone: @escaping () -> Void,
        onSessionEnd: @escaping (Failure) -> Void, api: ApiClient = ApiClient(tokens: FirebaseTokenSource())
    ) {
        self.onBack = onBack
        self.onDone = onDone
        self.onSessionEnd = onSessionEnd
        _model = State(initialValue: ResolveModel(id: id, api: api))
    }

    var body: some View {
        Frame(String(localized: "resolve_title"), onBack: onBack) {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        SectionLabel("resolve_outcome")
                        VStack(spacing: 8) {
                            ForEach(OUTCOMES, id: \.value) { outcome in
                                OutcomeRow(label: outcome.label, picked: model.outcome == outcome.value) {
                                    model.outcome = outcome.value
                                }
                            }
                        }
                        SnTextField(
                            // A paste past the limit is cut, as the dashboard's maxlength
                            text: Binding(get: { model.note }, set: { model.note = String($0.prefix(NOTE_MAX)) }),
                            label: "resolve_note", mono: false, multiline: true, capitalization: .sentences
                        )
                        .padding(.top, 12)
                        Text(verbatim: localized("note_count", model.note.count, NOTE_MAX))
                            .textStyle(Theme.mono).foregroundStyle(Theme.fgMuted)
                            .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 20)
                    .frame(maxWidth: 600)
                    .frame(maxWidth: .infinity)
                }
                .scrollDismissesKeyboard(.interactively)
                if let notice = model.notice { NoticeBanner(notice: notice) }
                ActionBar {
                    SnButton("send", kind: .success, fullWidth: true) { Task { await model.submit() } }
                        .disabled(!canSend(model.outcome, model.note) || model.sending)
                }
            }
        }
        // Not the profile: the page leaves for the home when it is done
        .environment(\.openProfile, nil)
        .onChange(of: model.notice) { _, notice in
            if case .ends(let failure)? = notice { onSessionEnd(failure) }
        }
        .onChange(of: model.done) { _, done in if done { onDone() } }
    }
}

/// The dashboard's square marker, not the system's round one.
private struct OutcomeRow: View {
    let label: String
    let picked: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Rectangle()
                    .fill(picked ? Theme.link : .clear)
                    .frame(width: 14, height: 14)
                    .overlay(Rectangle().strokeBorder(picked ? Theme.link : Theme.lineStrong, lineWidth: 2))
                Text(LocalizedStringKey(label)).textStyle(Theme.bodyLarge).foregroundStyle(Theme.fg)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 12)
            .frame(minHeight: 48)
            .overlay(Rectangle().strokeBorder(picked ? Theme.link : Theme.line, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(picked ? [.isSelected] : [])
    }
}
