import SwiftUI

/// One incident on the DAS phone (UC-11, UC-12): what happened, how to get in, who to call, what
/// was said. One scrolling page; the action that the status allows stays pinned under it. Ported
/// from android/app's das/IncidentScreen.kt.
struct IncidentView: View {
    let id: String
    let onBack: () -> Void
    let onResolve: (String) -> Void
    let onSessionEnd: (Failure) -> Void

    @State private var model: IncidentModel

    init(
        id: String, onBack: @escaping () -> Void, onResolve: @escaping (String) -> Void,
        onSessionEnd: @escaping (Failure) -> Void, api: ApiClient = ApiClient(tokens: FirebaseTokenSource())
    ) {
        self.id = id
        self.onBack = onBack
        self.onResolve = onResolve
        self.onSessionEnd = onSessionEnd
        _model = State(initialValue: IncidentModel(id: id, api: api))
    }

    var body: some View {
        let title = if case .ready(let page, _) = model.page { page.senior.fullName } else { "" }
        Frame(title, onBack: onBack) {
            LoadBody(load: model.page, onRetry: { Task { await model.load() } }, onSessionEnd: onSessionEnd) {
                incident in
                IncidentBody(
                    incident: incident, now: model.now, notice: model.notice, taking: model.taking,
                    onTake: { Task { await model.take() } }, onResolve: { onResolve(id) })
            }
        }
        .reread { await model.load() }
        .onChange(of: model.notice) { _, notice in
            if case .ends(let failure)? = notice { onSessionEnd(failure) }
        }
    }
}

/// The page, its notice and the pinned bar, apart from the model so it can be drawn from fixtures.
struct IncidentBody: View {
    let incident: IncidentPage
    let now: Date
    let notice: DasNotice?
    let taking: Bool
    let onTake: () -> Void
    let onResolve: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Summary(incident: incident, now: now)
                    Access(incident: incident)
                    Phones(incident: incident)
                    if let event = incident.event { EventSection(event: event) }
                    Calls(calls: incident.calls)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 20)
                .frame(maxWidth: 600)
                .frame(maxWidth: .infinity)
            }
            if let notice { NoticeBanner(notice: notice) }
            switch actFor(incident.status) {
            case .take?:
                ActionBar { SnButton("take", kind: .danger, fullWidth: true, action: onTake).disabled(taking) }
            case .resolve?:
                // The next step, as the dashboard's card; green is for Trimite
                ActionBar { SnButton("resolve", kind: .link, fullWidth: true, action: onResolve) }
            // Resolved meanwhile, or a status this build does not know
            case nil: EmptyView()
            }
        }
    }
}

/// The pinned bar under the page: the one action the status allows (design §"The incident page").
struct ActionBar<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        VStack(spacing: 0) {
            Rule()
            content.padding(.horizontal, 16).padding(.vertical, 12)
        }
        .background(Theme.subtle)
    }
}

/// A refused command, in the dashboard's words. `.ends` shows nothing: sign-in follows.
struct NoticeBanner: View {
    let notice: DasNotice

    var body: some View {
        switch notice {
        case .takenBy(let name): Banner(verbatim: localized("taken_by_other", name), tone: .galben)
        case .says(let key): Banner(key, tone: .galben)
        case .ends: EmptyView()
        }
    }
}

/// With the date, as the dashboard's `time`: an incident can stay open past midnight.
private func dated(_ iso: String) -> String {
    guard let at = instant(iso) else { return iso }
    return agoText(.on(at))
}

/// The status, the reason and the senior's own words.
private struct Summary: View {
    let incident: IncidentPage
    let now: Date

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            WrappingRow(spacing: 8, lineSpacing: 6) {
                StatusChip(status: incident.status, takenByName: incident.takenByName)
                if incident.status == OPEN, let since = ago(incident.openedAt, now: now) {
                    Text(verbatim: agoText(since)).textStyle(Theme.bodySmall).foregroundStyle(Theme.fgMuted)
                }
                if callLive(incident.calls) { Chip("call_live", tone: .galben) }
            }
            Text(verbatim: incident.reason).textStyle(Theme.titleLarge).foregroundStyle(Theme.fg)
            if let words = seniorsWords(incident.calls) {
                Text(verbatim: "„\(words)”")
                    .textStyle(Theme.bodyLarge).foregroundStyle(Theme.fg)
                    .padding(.leading, 15).padding(.trailing, 12).padding(.vertical, 10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.card)
                    .overlay(alignment: .leading) { Rectangle().fill(Tone.rosu.dot).frame(width: 3) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct Value: View {
    let text: String

    var body: some View { Text(verbatim: text).textStyle(Theme.bodyLarge).foregroundStyle(Theme.fg) }
}

/// The address with what it takes to get in (G13), and Maps.
private struct Access: View {
    let incident: IncidentPage

    @Environment(\.openURL) private var openURL

    var body: some View {
        let s = incident.senior
        SectionLabel("section_access").padding(.top, 20)
        VStack(spacing: 0) {
            // The section's last row takes the 2pt rule, whichever details are filled in
            let tail = s.keyHolder == nil && s.landmark == nil
            FieldRow("label_address", last: tail && s.intercomCode == nil) {
                Value(
                    text: place(
                        street: s.street, streetNumber: s.streetNumber, block: s.block, staircase: s.staircase,
                        floor: s.floor, apartment: s.apartment))
            }
            if let code = s.intercomCode {
                FieldRow("label_intercom", last: tail) {
                    Text(verbatim: code).textStyle(Theme.mono).foregroundStyle(Theme.fg)
                }
            }
            if let holder = s.keyHolder { FieldRow("label_key_holder", last: s.landmark == nil) { Value(text: holder) } }
            if let landmark = s.landmark { FieldRow("label_landmark", last: true) { Value(text: landmark) } }
        }
        if let link = mapsUrl(s, incident.event), let url = URL(string: link) {
            SnButton("open_in_maps", kind: .link, fullWidth: true) { openURL(url) }
        }
    }
}

/// The senior first, then each caregiver, each with *Apelează* (UC-11 step 3).
private struct Phones: View {
    let incident: IncidentPage

    var body: some View {
        SectionLabel("label_phone").padding(.top, 20)
        VStack(spacing: 0) {
            PersonRow(e164: incident.senior.phone, last: incident.caregivers.isEmpty) {
                Text(verbatim: incident.senior.fullName).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                HStack(spacing: 8) { PhoneNumber(e164: incident.senior.phone, landline: incident.senior.landline) }
            }
            ForEach(Array(incident.caregivers.enumerated()), id: \.offset) { i, c in
                PersonRow(e164: c.phone, last: i == incident.caregivers.count - 1) {
                    Text(verbatim: [c.displayName, c.relation].compactMap { $0 }.joined(separator: " · "))
                        .textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                    Text(verbatim: formatPhone(c.phone)).textStyle(Theme.mono).foregroundStyle(Theme.fgSoft)
                }
            }
        }
    }
}

private struct PersonRow<Content: View>: View {
    let e164: String
    let last: Bool
    @ViewBuilder let content: Content

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) { content }
                    .frame(maxWidth: .infinity, alignment: .leading)
                CallButton(e164: e164)
            }
            .padding(.vertical, 12)
            Rule(strong: last)
        }
    }
}

/// What set the incident off, and where (G16).
private struct EventSection: View {
    let event: TriggerEvent

    var body: some View {
        SectionLabel("section_event").padding(.top, 20)
        let place = location(event)
        VStack(spacing: 0) {
            FieldRow("event_type") { Value(text: labelOf(event.type, in: EVENT_LABELS)) }
            FieldRow("event_measured_at", last: place == nil) {
                Text(verbatim: dated(event.measuredAt)).textStyle(Theme.mono).foregroundStyle(Theme.fg)
            }
            if let place {
                FieldRow("event_location", last: true) {
                    let words =
                        if let m = place.accuracy {
                            localized("event_location_value", place.latitude, place.longitude, m)
                        } else {
                            localized("event_location_only", place.latitude, place.longitude)
                        }
                    Text(verbatim: words).textStyle(Theme.mono).foregroundStyle(Theme.fg)
                }
            }
        }
    }
}

/// Every call of the incident, newest first and open; older ones open on a tap.
private struct Calls: View {
    let calls: [IncidentCall]

    // Only the dispatcher's own taps are kept; the default follows the newest call
    @State private var toggled: [String: Bool] = [:]

    var body: some View {
        SectionLabel("section_calls").padding(.top, 20)
        if calls.isEmpty {
            Text("no_calls").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgMuted)
        } else {
            let newest = newestFirst(calls)
            ForEach(newest, id: \.id) { call in
                let open = expanded(call.id, newestId: newest[0].id, toggled: toggled)
                VStack(alignment: .leading, spacing: 8) {
                    Button { toggled[call.id] = !open } label: {
                        Text(verbatim: callLine(call)).textStyle(Theme.labelLarge).foregroundStyle(Theme.fgSoft)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(open ? [.isSelected] : [])
                    if open { Transcript(call: call) }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.subtle)
            }
        }
    }

    /// "Ceas · încercarea 1 · Cod roșu"; a call with no final code shows its state.
    private func callLine(_ call: IncidentCall) -> String {
        let outcome =
            call.finalSeverity.flatMap { CODE_LABELS[$0] }.map { String(localized: String.LocalizationValue($0)) }
            ?? labelOf(call.state, in: CALL_STATE_LABELS)
        return localized("call_line", labelOf(call.trigger, in: TRIGGER_LABELS), call.attempt, outcome)
    }
}
