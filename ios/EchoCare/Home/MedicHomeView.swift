import SwiftUI

/// The medic's home: her tasks, most important first, under the codes of her patients (design
/// 2026-11-13 medic home), ported from android/app's home/MedicHome.kt. A draft opens the form
/// `onDraft`, every other task the patient's page `onOpen`, where its action already is. `sent`
/// shows „Trimis la DAS.” for 5 s after the form submits. One column on any screen, kept readable
/// on an iPad; Monitorizare is where the iPad shows list and patient side by side.
struct MedicHomeView: View {
    let onMonitor: () -> Void
    let onNew: () -> Void
    let onOpen: (String) -> Void
    let onDraft: (String) -> Void
    let onSessionEnd: (Failure) -> Void
    @Binding var sent: Bool

    @State private var model: SeniorsModel

    init(
        onMonitor: @escaping () -> Void, onNew: @escaping () -> Void, onOpen: @escaping (String) -> Void,
        onDraft: @escaping (String) -> Void, onSessionEnd: @escaping (Failure) -> Void, sent: Binding<Bool>,
        api: ApiClient = ApiClient(tokens: FirebaseTokenSource())
    ) {
        self.onMonitor = onMonitor
        self.onNew = onNew
        self.onOpen = onOpen
        self.onDraft = onDraft
        self.onSessionEnd = onSessionEnd
        _sent = sent
        _model = State(initialValue: SeniorsModel(role: "medic", api: api))
    }

    var body: some View {
        Frame(String(localized: "medic_home")) {
            SnButton("new_patient", kind: .success, action: onNew)
        } content: {
            LoadBody(load: model.seniors, onRetry: { Task { await model.load() } }, onSessionEnd: onSessionEnd) {
                seniors in
                let tasks = tasksOf(seniors)
                ScrollView {
                    VStack(spacing: 0) {
                        if sent { Banner("sent", tone: .verde) }
                        VStack(alignment: .leading, spacing: 8) {
                            Strip(counts: countsOf(seniors), onMonitor: onMonitor)
                            SectionLabel(verbatim: localized("tasks_title", tasks.count))
                                .padding(.top, 12).padding(.bottom, 4)
                            if tasks.isEmpty {
                                Text("all_done").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgMuted)
                            }
                            ForEach(tasks, id: \.row.id) { task in
                                TaskRow(task: task) {
                                    if task.kind == .draft { onDraft(task.row.id) } else { onOpen(task.row.id) }
                                }
                            }
                        }
                        .padding(16)
                        .frame(maxWidth: 720)
                        .frame(maxWidth: .infinity)
                    }
                }
            }
        }
        .reread { await model.load() }
        .task(id: sent) {
            guard sent else { return }
            try? await Task.sleep(for: .seconds(5))
            if !Task.isCancelled { sent = false }
        }
    }
}

/// The codes of her patients and those at DAS, each only above zero, and the way to all of them.
private struct Strip: View {
    let counts: Counts
    let onMonitor: () -> Void

    var body: some View {
        // The chips are padded down to the middle of the 48pt button: WrappingRow aligns tops
        WrappingRow(spacing: 8, lineSpacing: 8) {
            if counts.red > 0 { Chip(verbatim: localized("count_red", counts.red), tone: .rosu).padding(.top, 13) }
            if counts.yellow > 0 {
                Chip(verbatim: localized("count_yellow", counts.yellow), tone: .galben).padding(.top, 13)
            }
            if counts.green > 0 {
                Chip(verbatim: localized("count_green", counts.green), tone: .verde).padding(.top, 13)
            }
            if counts.atDas > 0 {
                Chip(verbatim: localized("count_at_das", counts.atDas), tone: .link).padding(.top, 13)
            }
            SnButton("all_patients", kind: .link, action: onMonitor)
        }
    }
}

/// One task: a 4pt bar by kind, who, what is waiting, and the button that goes to it.
private struct TaskRow: View {
    let task: MedicTask
    let onGo: () -> Void

    var body: some View {
        let (bar, line, action): (Color, LocalizedStringKey, LocalizedStringKey) =
            switch task.kind {
            case .confirm: (Theme.link, "task_confirm", "do_review")
            case .analysisFailed: (Theme.link, "task_failed", "do_open")
            case .wrongNumber: (Theme.galben, "task_wrong_number", "do_correct")
            case .unreachable: (Theme.galben, "task_unreachable", "call_again")
            case .draft: (Theme.lineStrong, "task_draft", "do_continue")
            }
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                // A draft may not have its form of address yet
                if !task.row.formOfAddress.trimmingCharacters(in: .whitespaces).isEmpty {
                    Text(verbatim: task.row.formOfAddress).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
                }
                Text(verbatim: task.row.fullName).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgMuted)
                Text(line).textStyle(Theme.bodyMedium).foregroundStyle(Theme.fg)
            }
            .padding(12)
            .padding(.leading, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            SnButton(action, kind: .outline, action: onGo).padding(.trailing, 12)
        }
        .background(Theme.card)
        .overlay(alignment: .leading) { Rectangle().fill(bar).frame(width: 4) }
    }
}
