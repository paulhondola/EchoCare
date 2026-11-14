import Testing

@testable import EchoCare

// Design §5.7: the medic's medical record section. Ported from Android's home/MedicalTest.kt.
struct MedicalTests {
    private func record(_ state: String) -> MedicalRecord {
        MedicalRecord(state: state, uploadedAt: "2026-11-13T10:00:00Z")
    }

    private func item(_ question: String, included: Bool = true) -> MedicalItem {
        MedicalItem(condition: "c", question: question, worrying: "w", included: included)
    }

    @Test func `no record is none`() {
        #expect(stageOf(nil, seniorState: "active") == .none)
    }

    @Test func `pending waits for DAS while the senior is a draft or submitted`() {
        #expect(stageOf(record("pending"), seniorState: "draft") == .waitingForDas)
        #expect(stageOf(record("pending"), seniorState: "submitted") == .waitingForDas)
    }

    @Test func `pending analyzes once the senior is accepted or active`() {
        #expect(stageOf(record("pending"), seniorState: "accepted") == .analyzing)
        #expect(stageOf(record("pending"), seniorState: "active") == .analyzing)
    }

    @Test func `pending is never analyzed for a senior the server does not analyze`() {
        for state in ["refused", "withdrawn", "wrong_number", "unreachable", "new_state"] {
            #expect(stageOf(record("pending"), seniorState: state) == .notAnalyzed)
        }
    }

    @Test func `review, confirmed and failed`() {
        #expect(stageOf(record("review"), seniorState: "active") == .review)
        #expect(stageOf(record("confirmed"), seniorState: "active") == .confirmed)
        #expect(stageOf(record("failed"), seniorState: "active") == .failed)
    }

    @Test func `an unknown state is analyzing`() {
        #expect(stageOf(record("something_new"), seniorState: "active") == .analyzing)
    }

    @Test func `the confirm form trims, keeps order and included`() {
        let edited = [item("  a  "), item(" b", included: false), item("c ")]
        let form = confirmFormOf(edited, stored: edited)
        #expect(form.items.map(\.question) == ["a", "b", "c"])
        #expect(form.items.map(\.included) == [true, false, true])
    }

    @Test func `a blanked excluded item sends its stored question`() {
        let stored = [item("a"), item("kept", included: false)]
        let edited = [item(" a2 "), item("  ", included: false)]
        #expect(confirmFormOf(edited, stored: stored).items.map(\.question) == ["a2", "kept"])
    }

    @Test func `a reread with fewer stored items does not crash the confirm form`() {
        let edited = [item("a"), item("  ", included: false)]
        let form = confirmFormOf(edited, stored: [item("a")])
        #expect(form.items.map(\.question) == ["a", ""])
    }

    @Test func `the confirm form sends an edited worry and the profile it reviewed`() {
        var worried = item("a")
        worried.worrying = " Da "
        var blank = item("b")
        blank.worrying = "  "
        let edited = [worried, blank]
        let form = confirmFormOf(edited, stored: edited, analyzedAt: "2026-11-13T10:00:00Z")
        #expect(form.items.map(\.worrying) == ["Da", nil])
        #expect(form.analyzedAt == "2026-11-13T10:00:00Z")
    }

    @Test func `reanalyzing a confirmed profile waits for Modifica`() {
        #expect(!canReanalyze(.confirmed, editing: false))
        #expect(canReanalyze(.confirmed, editing: true))
        #expect(canReanalyze(.review, editing: false))
        #expect(canReanalyze(.failed, editing: false))
        #expect(!canReanalyze(.analyzing, editing: false))
    }

    @Test func `an included blank question blocks confirming`() {
        #expect(!canConfirm([item("a"), item("  ")]))
        #expect(canConfirm([item("a"), item("", included: false)]))
    }
}
