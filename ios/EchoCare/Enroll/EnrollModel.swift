import Foundation
import Observation

/// What the form's own read holds: nothing, only that it went through (Android's `Load<Unit>`).
struct Opened: Equatable, Sendable {}

/// „Pacient nou” and its edits: the four steps of seniors §9.2, ported from
/// android/app/.../enroll/EnrollViewModel.kt. Each command is one `async` call, one at a time
/// (SE14), whose refusal becomes what seniors §9.3 shows for it.
@Observable @MainActor
final class EnrollModel {
    /// The senior once saved. Nil on a new form until step 1's „Continuă” creates them.
    private(set) var id: String?

    /// Opened on a saved senior: from a draft's card or „Editează” (seniors §9.1).
    let existing: Bool

    /// The form itself: reading a saved senior, ready, or stopped by a refusal (seniors §8.2).
    private(set) var form: Load<Opened>

    private(set) var step = Step.senior

    /// The fields of steps 1 and 2, as typed.
    private(set) var values: [Field: String] = [:]

    /// What „Continuă” last saved. Back returns to it: what was typed since is dropped.
    private(set) var saved: [Field: String] = [:]

    /// „Echipamente”: the ticked boxes. Empty on a new form; nil for a saved senior whose
    /// equipment is not stated, which the form leaves alone until a box is ticked (design
    /// 2026-11-14).
    private(set) var equipment: Set<String>? = []

    private var savedEquipment: Set<String>? = []

    private(set) var state = "draft"

    private(set) var caregivers: [Caregiver] = []

    func tick(_ item: String, _ on: Bool) {
        let now = equipment ?? []
        equipment = on ? now.union([item]) : now.subtracting([item])
    }

    /// Step 3's row for a new caregiver.
    private(set) var adding: [Field: String] = [:]

    /// Step 4's summary, read again each time the step opens.
    private(set) var review: Load<SeniorPage> = .loading

    /// A request in flight disables „Continuă”, „Adaugă” and „Trimite la DAS” (SE14).
    private(set) var busy = false

    /// The server's texts (`Localizable.xcstrings` keys) under fields, until the field is typed in
    /// again.
    private(set) var errors: [Field: String] = [:]

    private(set) var notice: Notice?

    /// The optional medical record PDF: sending, sent, and the line (a key) for a refusal (design §5.7).
    private(set) var uploading = false
    private(set) var medicalSent = false
    private(set) var medicalNotice: String?

    private(set) var submitted = false

    private let api: ApiClient
    /// Step 4 was entered during a command: its summary is read once the command is over.
    private var rereadAfter = false

    init(seniorId: String?, api: ApiClient = ApiClient(tokens: FirebaseTokenSource())) {
        self.api = api
        id = seniorId
        existing = seniorId != nil
        form = seniorId == nil ? .ready(Opened()) : .loading
    }

    var isDraft: Bool { state == "draft" }

    /// The line over the buttons is „Lipsesc: …”.
    var noticeIsMissing: Bool {
        if case .missing = notice { true } else { false }
    }

    /// Reads the saved senior into the form, at step 1. Also „Reîncercați”.
    func open() async {
        guard let id else { return }
        form = .loading
        let api = api
        switch await answer({ try await api.senior(id: id) }) {
        case .ok(let page):
            show(page)
            form = .ready(Opened())
        case .no(let failure):
            form = .failed(failure)
        }
    }

    func type(_ field: Field, _ text: String) {
        if REGISTRATION.contains(field) { values[field] = text } else { adding[field] = text }
        errors[field] = nil
    }

    /// „Continuă”: steps 1 and 2 save first; step 3 sends nothing (seniors §9.2).
    func next() async {
        let api = api
        switch saveFor(step, id: id, values, equipment: equipment) {
        case .create(let body):
            await command(.save, { try await api.createSenior(body) }, done: savedAndNext)
        case .update(let id, let body):
            await command(
                .save, { try await api.updateSenior(id: id, body: body) }, done: savedAndNext)
        case .none:
            go(step.next)
            await rereadIfDue()
        }
    }

    /// Back: the previous step, or false on step 1, where the form closes.
    func back() -> Bool {
        // The answer in flight would land on another step
        if busy { return true }
        if step == .senior { return false }
        values = saved
        equipment = savedEquipment
        adding = [:]
        go(step.previous)
        return true
    }

    func add() async {
        guard let id else { return }
        let api = api
        let body = caregiverOf(adding)
        await command(.add, { try await api.addCaregiver(id: id, body: body) }) {
            [self] caregiver in
            caregivers.append(caregiver)
            adding = [:]
        }
    }

    func remove(_ caregiver: Caregiver) async {
        guard let id else { return }
        let api = api
        await command(.remove, { try await api.removeCaregiver(id: id, userId: caregiver.userId) })
        {
            [self] _ in caregivers.removeAll { $0.userId == caregiver.userId }
        }
    }

    /// The PDF of step 4. A failure shows a line and never blocks „Trimite la DAS”.
    func uploadPdf(_ pdf: Data?) async {
        guard let id, !uploading else { return }
        medicalNotice = nil
        guard let pdf, pdf.count <= MAX_PDF_BYTES else {
            medicalNotice = pdf == nil ? "medical_upload_failed" : "medical_too_large"
            return
        }
        uploading = true
        let api = api
        switch await send({ try await api.uploadMedicalRecord(id: id, pdf: pdf) }) {
        case .ok: medicalSent = true
        case .no: medicalNotice = "medical_upload_failed"
        }
        uploading = false
    }

    /// „Trimite la DAS”: `draft` → `submitted`; the screen then returns to the home.
    func submit() async {
        guard let id else { return }
        let api = api
        await command(.submit, { try await api.submit(id: id) }) { [self] _ in submitted = true }
    }

    /// „Salvează semnătura” on step 4 (G7, UC-01 step 5). The summary is read again on success, so
    /// the pad gives way to the date; a refusal shows its line and the pad keeps the drawing.
    func sign(_ form: SignatureForm) async {
        guard let id else { return }
        let api = api
        await command(.sign, { try await api.sign(id: id, body: form) }) { [self] _ in
            rereadAfter = true
        }
    }

    /// Step 4's summary: GET seniors/{id}, which also refreshes the other steps.
    func reread() async {
        guard let id else { return }
        review = .loading
        let api = api
        let read = await answer { try await api.senior(id: id) }
        if case .ok(let page) = read { show(page) }
        review = review.after(read)
    }

    private func savedAndNext(_ page: SeniorPage) {
        show(page)
        go(step.next)
    }

    /// Moves to `to`; step 4's summary is read when the command (if any) is over.
    private func go(_ to: Step) {
        step = to
        errors = [:]
        notice = nil
        if to == .review { rereadAfter = true }
    }

    private func rereadIfDue() async {
        guard rereadAfter else { return }
        rereadAfter = false
        await reread()
    }

    /// The senior as the server holds them: what the fields return to on Back.
    private func show(_ page: SeniorPage) {
        id = page.id
        state = page.state
        caregivers = page.caregivers
        saved = valuesOf(page)
        values = saved
        savedEquipment = equipmentIn(page)
        equipment = savedEquipment
    }

    /// One request at a time (SE14). A refusal becomes what seniors §9.3 shows for it.
    private func command<T: Sendable>(
        _ action: Action, _ call: () async throws -> T, done: (T) -> Void
    ) async {
        if busy { return }
        busy = true
        errors = [:]
        notice = nil
        switch await send(call) {
        case .ok(let value): done(value)
        case .no(let refusal): refused(thenAfter(action, refusal))
        }
        busy = false
        // After busy, as Android's launched read: Back works while step 4 loads
        await rereadIfDue()
    }

    private func refused(_ then: Then) {
        switch then {
        case .mark(let marks): errors = marks
        case .show(let notice): self.notice = notice
        case .reread: go(.review)
        case .stop(let failure): form = .failed(failure)
        }
    }
}
