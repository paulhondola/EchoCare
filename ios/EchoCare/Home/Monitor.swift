import SwiftUI

/// Monitorizare: the medic's patients by need, and on an iPad (a regular width) the chosen patient
/// beside them, list about 40%, patient 60% (UC-12, 03 §7, design 2026-11-04 medic tablet panel).
/// On a phone a tap opens the patient's own page through `onOpen`. Ported from android/app's
/// home/Monitor.kt, which switches at 840dp; here the size class decides, so an iPad in Split View
/// narrow enough to be compact gets the phone's list.
struct MonitorView: View {
    let onBack: () -> Void
    let onOpen: (String) -> Void
    let onNew: () -> Void
    let onEdit: (String) -> Void
    let onSessionEnd: (Failure) -> Void
    private let api: ApiClient

    @State private var model: SeniorsModel
    @Environment(\.horizontalSizeClass) private var sizeClass

    init(
        onBack: @escaping () -> Void, onOpen: @escaping (String) -> Void, onNew: @escaping () -> Void,
        onEdit: @escaping (String) -> Void, onSessionEnd: @escaping (Failure) -> Void,
        api: ApiClient = ApiClient(tokens: FirebaseTokenSource())
    ) {
        self.onBack = onBack
        self.onOpen = onOpen
        self.onNew = onNew
        self.onEdit = onEdit
        self.onSessionEnd = onSessionEnd
        self.api = api
        _model = State(initialValue: SeniorsModel(role: "medic", api: api))
    }

    var body: some View {
        Frame(String(localized: "monitor"), onBack: onBack) {
            if case .loading = model.seniors {
                PlaceholderCards(count: 6)
            } else {
                LoadBody(load: model.seniors, onRetry: { Task { await model.load() } }, onSessionEnd: onSessionEnd) {
                    seniors in
                    let groups = panel(seniors)
                    if groups.isEmpty {
                        Message("no_patients_yet") { SnButton("new_patient", action: onNew) }
                    } else if sizeClass == .regular {
                        GeometryReader { geometry in
                            HStack(spacing: 0) {
                                PatientList(groups: groups, selected: model.selected) { model.selected = $0 }
                                    .frame(width: geometry.size.width * 0.4)
                                Rectangle().fill(Theme.line).frame(width: 2)
                                Group {
                                    if let id = model.selected {
                                        // One page per patient, so a new choice starts clean
                                        SelectedPatient(
                                            id: id, api: api, onSessionEnd: onSessionEnd, onEdit: onEdit,
                                            onChanged: { await model.load() }
                                        )
                                        .id(id)
                                    } else {
                                        Message("pick_patient")
                                    }
                                }
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                            }
                        }
                    } else {
                        PatientList(groups: groups, selected: nil, onPick: onOpen)
                    }
                }
            }
        }
        .reread { await model.load() }
    }
}

/// The patient in Monitorizare's right pane, with a page model of its own.
private struct SelectedPatient: View {
    let id: String
    let onSessionEnd: (Failure) -> Void
    let onEdit: (String) -> Void
    let onChanged: () async -> Void

    @State private var model: SeniorDetailModel

    init(
        id: String, api: ApiClient, onSessionEnd: @escaping (Failure) -> Void, onEdit: @escaping (String) -> Void,
        onChanged: @escaping () async -> Void
    ) {
        self.id = id
        self.onSessionEnd = onSessionEnd
        self.onEdit = onEdit
        self.onChanged = onChanged
        _model = State(initialValue: SeniorDetailModel(api: api))
    }

    var body: some View {
        PatientPane(id: id, model: model, onSessionEnd: onSessionEnd, onEdit: onEdit, onChanged: onChanged)
    }
}

private struct PatientList: View {
    let groups: [(group: PatientGroup, rows: [SeniorRow])]
    let selected: String?
    let onPick: (String) -> Void

    @State private var showInactive = false

    var body: some View {
        let now = Date()
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                ForEach(groups, id: \.group) { group, rows in
                    SectionLabel(LocalizedStringKey(group.title)).padding(.top, 12).padding(.bottom, 4)
                    // Inactive starts collapsed: those patients need nothing from her
                    if group != .inactive || showInactive {
                        ForEach(rows, id: \.id) { row in
                            PatientCard(row: row, group: group, selected: row.id == selected, now: now) {
                                onPick(row.id)
                            }
                        }
                    }
                    if group == .inactive {
                        SnButton(
                            showInactive ? "hide" : LocalizedStringKey(localized("show_n", rows.count)), kind: .link
                        ) { showInactive.toggle() }
                    }
                }
            }
            .padding(16)
        }
    }
}

/// One patient: a 4pt bar and tint by need, who, why, since when (UC-12, 03 §7).
struct PatientCard: View {
    let row: SeniorRow
    let group: PatientGroup
    let selected: Bool
    let now: Date
    let onTap: () -> Void

    var body: some View {
        let (bar, tint): (Color, Color) =
            switch group {
            case .urgent where row.code == "yellow": (Theme.galben, Tone.galben.fill)
            case .urgent: (Theme.rosu, Tone.rosu.fill)
            case .toResolve: (Theme.link, Theme.card)
            default: (Theme.line, Theme.card)
            }
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 6) {
                if row.state == "active", row.code != nil {
                    CodeLabel(code: row.code, reason: row.reason)
                } else if STATE_LABELS[row.state] != nil {
                    StateLabel(state: row.state)
                } else {
                    // A state this build does not know, in Inactivi under its raw name (UC-12)
                    Chip(verbatim: row.state, tone: .muted)
                }
                Text(verbatim: row.formOfAddress).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                Text(verbatim: row.fullName).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgMuted)
                if let line = says(row.state) {
                    Text(LocalizedStringKey(line)).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fg)
                }
                let at: String? =
                    switch group {
                    case .urgent: row.since
                    case .atDas: row.submittedAt
                    default: nil
                    }
                if let at, let since = ago(at, now: now) {
                    Text(verbatim: agoText(since)).textStyle(Theme.bodySmall).foregroundStyle(Theme.fgMuted)
                }
                if row.watchState != "ok", let chip = watchChip(row.watchState) {
                    Chip(LocalizedStringKey(chip.label), tone: chip.tone)
                }
            }
            .padding(12)
            .padding(.leading, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(tint)
            .overlay(alignment: .leading) { Rectangle().fill(bar).frame(width: 4) }
            .overlay(Rectangle().strokeBorder(selected ? Theme.link : .clear, lineWidth: 2))
            .opacity(group == .inactive ? 0.6 : 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// Grey boxes where the cards will be while the list loads: no spinner (UC-12).
struct PlaceholderCards: View {
    let count: Int

    var body: some View {
        VStack(spacing: 8) {
            ForEach(0..<count, id: \.self) { _ in
                Rectangle().fill(Theme.card).frame(height: 88)
            }
        }
        .padding(16)
        .frame(maxHeight: .infinity, alignment: .top)
        .accessibilityHidden(true)
    }
}
