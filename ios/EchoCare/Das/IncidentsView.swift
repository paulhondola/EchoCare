import SwiftUI

/// The DAS home: red incidents, open then in progress, the longest wait first (UC-12), ported from
/// android/app's das/IncidentsScreen.kt. One column on a phone, two or more on an iPad. Android's
/// `NotificationsPrompt` has no iOS counterpart: no push (design, Out of scope).
struct IncidentsView: View {
    let onOpen: (String) -> Void
    let onSessionEnd: (Failure) -> Void

    @State private var model: IncidentsModel

    init(
        onOpen: @escaping (String) -> Void, onSessionEnd: @escaping (Failure) -> Void,
        api: ApiClient = ApiClient(tokens: FirebaseTokenSource())
    ) {
        self.onOpen = onOpen
        self.onSessionEnd = onSessionEnd
        _model = State(initialValue: IncidentsModel(api: api))
    }

    var body: some View {
        Frame(String(localized: "role_das")) {
            LoadBody(load: model.incidents, onRetry: { Task { await model.load() } }, onSessionEnd: onSessionEnd) {
                rows in
                IncidentList(rows: rows, now: model.now, onOpen: onOpen)
            }
        }
        .reread { await model.load() }
    }
}

/// The two sections of cards; `Message` when there is nothing to do.
struct IncidentList: View {
    let rows: [IncidentRow]
    let now: Date
    let onOpen: (String) -> Void

    var body: some View {
        let s = sections(rows)
        if s.open.isEmpty && s.inProgress.isEmpty {
            Message("no_incidents")
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    section("incidents_open", s.open)
                    section("incidents_in_progress", s.inProgress)
                }
                .padding(16)
            }
        }
    }

    @ViewBuilder
    private func section(_ key: String, _ rows: [IncidentRow]) -> some View {
        if !rows.isEmpty {
            SectionLabel(verbatim: localized(key, rows.count)).padding(.top, 8).padding(.bottom, 4)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 320), spacing: 8)], spacing: 8) {
                ForEach(rows, id: \.id) { row in IncidentCard(row: row, now: now) { onOpen(row.id) } }
            }
        }
    }
}

/// The dashboard's card, with a bar in the status's colour (IncidentCard.svelte).
private struct IncidentCard: View {
    let row: IncidentRow
    let now: Date
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 6) {
                Text(verbatim: row.seniorName).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                Text(verbatim: row.reason).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgSoft)
                // Whole chips wrap to a second line on a narrow phone, never their words
                WrappingRow(spacing: 8, lineSpacing: 6) {
                    if let since = ago(row.openedAt, now: now) {
                        Text(verbatim: agoText(since)).textStyle(Theme.bodySmall).foregroundStyle(Theme.fgMuted)
                    }
                    StatusChip(status: row.status, takenByName: row.takenByName)
                    HandoverChip(answered: row.handoverAnswered)
                }
            }
            .padding(.leading, 17)
            .padding(.trailing, 14)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card)
            .overlay(alignment: .leading) { Rectangle().fill(statusTone(row.status).dot).frame(width: 3) }
            .overlay(Rectangle().strokeBorder(Theme.line, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// Deschis, În lucru · preluat de …, Rezolvat; a status this build does not know shows as it is.
struct StatusChip: View {
    let status: String
    let takenByName: String?

    var body: some View {
        let label =
            switch status {
            case OPEN: String(localized: "status_open")
            // As the dashboard: a taker it cannot name is „un dispecer”
            case IN_PROGRESS: localized("status_taken_by", takenByName ?? String(localized: "a_dispatcher"))
            case "resolved": String(localized: "status_resolved")
            default: status
            }
        Chip(verbatim: label, tone: statusTone(status))
    }
}

/// As the dashboard's card: whether the hand-over was answered on any of the calls (04 §1).
private struct HandoverChip: View {
    let answered: Bool

    var body: some View {
        if answered {
            Chip("handover_yes", tone: .verde)
        } else {
            Chip("handover_no", tone: .galben)
        }
    }
}
