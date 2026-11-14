import SwiftUI

/// The caregiver's home: their seniors as cards (seniors §8.2, SE20), ported from android/app's
/// home/SeniorsScreen.kt. One column on a phone, two or more on an iPad. The medic has her own
/// home (MedicHomeView.swift, UC-12). Android's `NotificationsPrompt` has no iOS counterpart: no
/// push (design, Out of scope).
struct SeniorsView: View {
    let onOpen: (String) -> Void
    let onSessionEnd: (Failure) -> Void

    @State private var model: SeniorsModel

    init(
        role: String, onOpen: @escaping (String) -> Void, onSessionEnd: @escaping (Failure) -> Void,
        api: ApiClient = ApiClient(tokens: FirebaseTokenSource())
    ) {
        self.onOpen = onOpen
        self.onSessionEnd = onSessionEnd
        _model = State(initialValue: SeniorsModel(role: role, api: api))
    }

    var body: some View {
        Frame(String(localized: "caregiver_home")) {
            LoadBody(load: model.seniors, onRetry: { Task { await model.load() } }, onSessionEnd: onSessionEnd) {
                seniors in
                if seniors.isEmpty {
                    Message("no_seniors")
                } else {
                    ScrollView {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 8)], spacing: 8) {
                            ForEach(seniors, id: \.id) { senior in
                                SeniorCard(senior: senior) { onOpen(senior.id) }
                            }
                        }
                        .padding(16)
                    }
                }
            }
        }
        .reread { await model.load() }
    }
}

/// The dashboard's card: a bar down the left edge in the code's colour, else the state's.
private struct SeniorCard: View {
    let senior: SeniorRow
    let onTap: () -> Void

    var body: some View {
        let tone = senior.code.flatMap { CODE_TONES[$0] } ?? STATE_TONES[senior.state] ?? .muted
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 6) {
                Text(verbatim: senior.formOfAddress).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                Text(verbatim: senior.fullName).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgMuted)
                HStack(spacing: 8) { PhoneNumber(e164: senior.phone, landline: senior.landline) }
                StateLabel(state: senior.state)
                CodeLabel(code: senior.code, reason: senior.reason)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .padding(.leading, 3)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card)
            .overlay(alignment: .leading) { Rectangle().fill(tone.dot).frame(width: 3) }
            .overlay(Rectangle().strokeBorder(Theme.line, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
