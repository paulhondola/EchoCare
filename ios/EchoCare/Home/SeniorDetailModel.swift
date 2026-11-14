import Foundation
import Observation

/// One senior's page opened from a list, the caregiver's and the medic's: GET /seniors/{id}
/// (seniors §3.3), ported from the id half of android/app/.../home/SeniorViewModel.kt. For the
/// medic it also holds her panel: the commands, every call's transcript and the medical record
/// (UC-04, UC-12, design §5.7). The senior's own home is `SeniorModel`.
@Observable @MainActor
final class SeniorDetailModel {
    private(set) var page: Load<SeniorPage> = .loading

    /// The call history (UC-12); nil until read.
    private(set) var calls: [CallRow]?

    /// A command in flight: „Sună din nou” and „Retrage” wait for it (UC-12).
    private(set) var busy = false

    /// The banner after a command that did not go through; nil after one that did.
    private(set) var notice: CommandOutcome?

    /// The form saved a new number for a senior to resolve: „Sună din nou” calls it (04 §2).
    private(set) var numberChanged = false

    /// Each call's transcript the medic opened, by call id, read once (04 §1).
    private(set) var transcripts: [String: Load<IncidentCall>] = [:]

    /// The medic's list read and this senior is not on it: someone she reaches by another grant,
    /// such as a caregiver's. Her page then shows no medic panel (UC-12).
    private(set) var notHers = false

    /// The medical record (design §5.7); nil until read, and for anyone but the medic.
    private(set) var medical: MedicalRecord?

    /// A `Localizable.xcstrings` key: why the last upload did not go (design §5.7).
    private(set) var uploadNotice: String?

    private let api: ApiClient
    private var reading: Task<Void, Never>?
    /// Whether the last load read the medical record: a command's reread does the same.
    private var readsMedical = false
    /// The number on the page when „Editează datele” was pressed, until a reread shows another.
    private var phoneBeforeEdit: String?

    init(api: ApiClient = ApiClient(tokens: FirebaseTokenSource())) {
        self.api = api
    }

    /// Reads the page and the calls, and with `medical` the record. A read still under way is out
    /// of date; left running, it could land after this one.
    func load(id: String, medical: Bool) async {
        readsMedical = medical
        reading?.cancel()
        let read = Task { await readAll(id: id, medical: medical) }
        reading = read
        await withTaskCancellationHandler { await read.value } onCancel: { read.cancel() }
    }

    private func readAll(id: String, medical readsRecord: Bool) async {
        let api = api
        let read = await answer { try await api.senior(id: id) }
        // A cancelled read says nothing about the connection
        guard !Task.isCancelled else { return }
        page = page.after(read)
        if case .ok(let senior) = read {
            noteNumber(senior)
            notice = noticeAfterRead(notice)
        }
        // A failed read keeps the last list, as the page keeps its last answer
        if case .ok(let rows) = await answer({ try await api.calls(id: id) }), !Task.isCancelled {
            calls = rows
        }
        guard readsRecord else { return }
        // A 204 is no record; a 404 or any other failure keeps the last (SeniorViewModel.kt)
        do {
            let record = try await api.medicalRecord(id: id)
            if !Task.isCancelled { medical = record }
        } catch {}
    }

    /// Sets `notHers` once the medic's list says `id` is not one of her patients.
    func checkHers(id: String) async {
        let api = api
        if case .ok(let rows) = await answer({ try await api.seniors(role: "medic") }) {
            notHers = !rows.contains { $0.id == id }
        }
    }

    /// „Editează datele”: remembers the number, to tell whether the form changed it.
    func editing() {
        if case .ready(let senior, _) = page { phoneBeforeEdit = senior.phone }
    }

    /// „Sună din nou”: queues a welcome call to the number on file, at once (UC-04, 04 §2).
    /// `onChanged` runs after an answer that may have moved the senior: a list beside the page
    /// rereads, so the patient changes group at once (UC-12).
    func callAgain(id: String, onChanged: @escaping () async -> Void = {}) async {
        let api = api
        await runCommand(id: id, onChanged: onChanged) { _ = try await api.callAgain(id: id) }
    }

    /// „Retrage”, after the dialog: the senior is called no more (04 §2). As `callAgain`.
    func withdraw(id: String, onChanged: @escaping () async -> Void = {}) async {
        let api = api
        await runCommand(id: id, onChanged: onChanged) { _ = try await api.withdraw(id: id) }
    }

    /// „Salvează semnătura”: posts the strokes the pad turned into `form` (G7, 04 §2). A failure
    /// shows its banner and the pad keeps its drawing; as `callAgain` otherwise.
    func sign(id: String, form: SignatureForm, onChanged: @escaping () async -> Void = {}) async {
        let api = api
        await runCommand(id: id, onChanged: onChanged) { try await api.sign(id: id, body: form) }
    }

    /// Uploads the PDF; over the limit nothing is sent (design §5.7).
    func uploadPdf(id: String, pdf: Data, onChanged: @escaping () async -> Void = {}) async {
        if pdf.count > MAX_PDF_BYTES {
            uploadNotice = "medical_too_large"
            return
        }
        let api = api
        // The upload's own line replaces the generic banner
        await runCommand(
            id: id, onChanged: onChanged,
            failed: {
                self.notice = nil
                self.uploadNotice = "medical_upload_failed"
            }
        ) { _ = try await api.uploadMedicalRecord(id: id, pdf: pdf) }
    }

    /// „Confirmă”: the medic's edits and choices, in the stored order (design §5.5).
    func confirmMedical(id: String, items: [MedicalItem]) async {
        let form = confirmFormOf(items, stored: medical?.items ?? items, analyzedAt: medical?.analyzedAt)
        let api = api
        await runCommand(id: id, onChanged: {}) { _ = try await api.confirmMedicalRecord(id: id, body: form) }
    }

    /// „Analizează din nou” (design §5.3).
    func reanalyzeMedical(id: String) async {
        let api = api
        await runCommand(id: id, onChanged: {}) { _ = try await api.reanalyzeMedicalRecord(id: id) }
    }

    /// „Transcriere”: reads the call's transcript once; a failed read is tried again on a tap.
    func openTranscript(callId: String) async {
        switch transcripts[callId] {
        case .ready, .loading: return
        default: break
        }
        transcripts[callId] = .loading
        let api = api
        let read = await answer { try await api.transcript(id: callId) }
        transcripts[callId] = Load.loading.after(read)
    }

    /// One command at a time. Any answer but `.offline` rereads the senior and runs `onChanged`.
    /// Busy until the page shows the answer: a second tap on the old page would post a second
    /// signature or withdraw again.
    private func runCommand(
        id: String, onChanged: () async -> Void, failed: () -> Void = {},
        _ call: () async throws -> Void
    ) async {
        guard !busy else { return }
        busy = true
        notice = nil
        uploadNotice = nil
        let outcome = await command(call)
        notice = outcome == .done ? nil : outcome
        if outcome != .done { failed() }
        if outcome != .offline {
            numberChanged = false
            await load(id: id, medical: readsMedical)
            await onChanged()
        }
        busy = false
    }

    /// A number other than the one before the edit, on a senior to resolve, shows the banner.
    private func noteNumber(_ senior: SeniorPage) {
        if let before = phoneBeforeEdit, senior.phone != before {
            numberChanged = isNewNumberToCall(before: before, now: senior)
            phoneBeforeEdit = nil
        }
        // „Sună din nou” or the scheduler moved them on: the hint no longer applies
        if senior.state != "wrong_number" && senior.state != "unreachable" { numberChanged = false }
    }
}
