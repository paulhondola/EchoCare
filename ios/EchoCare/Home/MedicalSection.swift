import SwiftUI
import UniformTypeIdentifiers

/// The bytes of the PDF at `url`, from the system file picker, or nil when it cannot be read.
/// Stops one byte past `MAX_PDF_BYTES`, so a huge file is never held whole; the caller refuses a
/// result over the limit. Android's `readPdf` (home/MedicalSection.kt).
func readPdf(_ url: URL) -> Data? {
    // A file from Files or iCloud Drive is outside the sandbox until this is granted
    let scoped = url.startAccessingSecurityScopedResource()
    defer { if scoped { url.stopAccessingSecurityScopedResource() } }
    guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
    defer { try? handle.close() }
    return try? handle.read(upToCount: MAX_PDF_BYTES + 1) ?? Data()
}

/// „Fișa medicală” on the medic's page: the PDF, the analysis state, and the questions to confirm
/// (design §5.7), ported from android/app's home/MedicalSection.kt. Items are read-only once
/// confirmed until „Modifică”. The PDF comes from the system file picker.
struct MedicalSection: View {
    let record: MedicalRecord?
    let seniorState: String
    let busy: Bool
    /// A `Localizable.xcstrings` key: why the last upload did not go.
    let uploadNotice: String?
    let onUpload: (Data) -> Void
    let onConfirm: ([MedicalItem]) -> Void
    let onReanalyze: () -> Void

    @State private var items: [MedicalItem] = []
    @State private var editing = false
    @State private var picking = false
    @Environment(\.openURL) private var openURL

    var body: some View {
        let stage = stageOf(record, seniorState: seniorState)
        VStack(alignment: .leading, spacing: 12) {
            SectionLabel("medical_section")
            Rule()
            if let line = stageLine(stage) {
                Text(LocalizedStringKey(line)).textStyle(Theme.bodyLarge).foregroundStyle(
                    Theme.fgSoft)
            }
            if let uploadNotice {
                Text(LocalizedStringKey(uploadNotice)).textStyle(Theme.bodyLarge).foregroundStyle(
                    Theme.galbenFg)
            }
            if stage == .review || stage == .confirmed {
                let open = stage == .review || editing
                ForEach(items.indices, id: \.self) { i in
                    ItemRow(item: $items[i], editable: open && !busy)
                    Rule(strong: false)
                }
                if open {
                    SnButton("medical_confirm", kind: .success) { onConfirm(items) }
                        .disabled(busy || !canConfirm(items))
                } else {
                    SnButton("medical_edit", kind: .outline) { editing = true }
                }
            }
            WrappingRow(spacing: 8, lineSpacing: 8) {
                if let link = record?.pdfUrl, let url = URL(string: link) {
                    SnButton("medical_open", kind: .link) { openURL(url) }
                }
                if canReanalyze(stage, editing: editing) {
                    SnButton("medical_reanalyze", kind: .outline, action: onReanalyze).disabled(
                        busy)
                }
                SnButton(record == nil ? "medical_upload" : "medical_replace", kind: .outline) {
                    picking = true
                }
                .disabled(busy)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 24)
        .fileImporter(isPresented: $picking, allowedContentTypes: [.pdf]) { result in
            if case .success(let url) = result, let pdf = readPdf(url) { onUpload(pdf) }
        }
        // A reread with new items replaces the edits; a new state or confirmation closes „Modifică”
        .onChange(of: record?.items, initial: true) { _, new in items = new ?? [] }
        .onChange(of: [record?.state, record?.confirmedAt]) { editing = false }
    }

    private func stageLine(_ stage: MedicalStage) -> String? {
        switch stage {
        case .waitingForDas: "medical_waiting"
        case .analyzing: "medical_analyzing"
        case .notAnalyzed: "medical_not_analyzed"
        case .review: "medical_review"
        case .failed: "medical_failed"
        case .none, .confirmed: nil
        }
    }
}

/// One condition: its name, the worry, the include box and the question the call will ask.
private struct ItemRow: View {
    @Binding var item: MedicalItem
    let editable: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                item.included.toggle()
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: item.included ? "checkmark.square.fill" : "square")
                        .font(.system(size: 20))
                        .foregroundStyle(item.included ? Theme.link : Theme.fgMuted)
                        .frame(width: 48, height: 48)
                    Text(verbatim: item.condition).textStyle(Theme.titleMedium).foregroundStyle(
                        Theme.fg
                    )
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(!editable)
            .accessibilityAddTraits(item.included ? .isSelected : [])
            // Editable with the question: an edited question needs its own worry (design §5.5)
            if !editable {
                Text(verbatim: "\(String(localized: "medical_worrying")): \(item.worrying)")
                    .textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgSoft).padding(.leading, 12)
            }
            if !item.evidence.trimmingCharacters(in: .whitespaces).isEmpty {
                Text(verbatim: item.evidence).textStyle(Theme.bodyLarge).foregroundStyle(
                    Theme.fgMuted
                )
                .padding(.leading, 12)
            }
            if editable {
                SnTextField(
                    text: $item.question, label: "medical_question", mono: false, multiline: true)
                SnTextField(
                    text: $item.worrying, label: "medical_worrying", mono: false, multiline: true)
            } else {
                Text(verbatim: item.question).textStyle(Theme.bodyLarge).foregroundStyle(Theme.fg)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .overlay(Rectangle().strokeBorder(Theme.line, lineWidth: 1))
            }
        }
    }
}
