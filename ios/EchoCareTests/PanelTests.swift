import Foundation
import Testing

@testable import EchoCare

// UC-12, 03 §7: the medic's panel groups, actions and the enrollment stages. Ported from Android's
// home/PanelTest.kt.
struct PanelTests {
    private func row(_ id: String, _ state: String, _ code: String? = nil, _ since: String? = nil)
        -> SeniorRow
    {
        SeniorRow(
            id: id, fullName: id, formOfAddress: "Dna", phone: "+40700000000", landline: false,
            state: state,
            code: code, since: since)
    }

    private func page(
        _ state: String, signedAt: String? = nil, createdAt: String? = nil,
        submittedAt: String? = nil,
        acceptedAt: String? = nil, consent: ConsentState? = nil, consentGivenAt: String? = nil
    ) -> SeniorPage {
        SeniorPage(
            id: "s", fullName: "S", formOfAddress: "Dna", phone: "+40700000000", landline: false,
            state: state,
            medic: Medic(displayName: "M"), createdAt: createdAt, submittedAt: submittedAt,
            acceptedAt: acceptedAt, consent: consent, consentGivenAt: consentGivenAt,
            signedAt: signedAt)
    }

    @Test func `a red is above a yellow is above everything`() {
        let rows = [
            row("g", "active", "green"), row("y", "active", "yellow"), row("r", "active", "red"),
        ]
        let first = panel(rows).first
        #expect(first?.group == .urgent)
        #expect(first?.rows.map(\.id) == ["r", "y"])
    }

    @Test func `the oldest red first`() {
        let rows = [
            row("none", "active", "red", nil),
            row("new", "active", "red", "2026-11-04T10:00:00Z"),
            row("old", "active", "red", "2026-11-04T08:00:00Z"),
        ]
        #expect(panel(rows).first?.rows.map(\.id) == ["old", "new", "none"])
    }

    @Test func `groups come in order and empty ones go`() {
        let rows = [
            row("a", "refused"), row("b", "submitted"), row("c", "active", "green"),
            row("d", "accepted"),
            row("e", "wrong_number"), row("f", "active", "red"), row("g", "draft"),
        ]
        #expect(
            panel(rows).map(\.group) == [
                .urgent, .toResolve, .inProgress, .green, .atDas, .inactive,
            ])
        #expect(!panel(rows).flatMap(\.rows).contains { $0.id == "g" })
    }

    @Test func `an unknown state is inactive`() {
        #expect(groupOf(row("x", "paused")) == .inactive)
        #expect(groupOf(row("w", "withdrawn")) == .inactive)
    }

    @Test func `active without a code is green`() {
        #expect(groupOf(row("x", "active")) == .green)
        #expect(groupOf(row("x", "active", "mystery")) == .green)
        #expect(groupOf(row("x", "draft")) == nil)
    }

    @Test func counts() {
        let rows = [
            row("1", "active", "red"), row("2", "active", "yellow"), row("3", "active", "yellow"),
            row("4", "wrong_number"), row("5", "unreachable"), row("6", "draft"),
            row("7", "active", "green"),
            row("8", "submitted"), row("9", "submitted"), row("10", "withdrawn", "green"),
        ]
        #expect(countsOf(rows) == Counts(red: 1, yellow: 2, green: 1, atDas: 2))
    }

    @Test func `actions by state`() {
        let table: [String: [PatientAction]] = [
            "wrong_number": [.callAgain, .edit],
            "unreachable": [.callAgain, .edit],
            "active": [.withdraw, .edit],
            "submitted": [.sign, .edit],
            "accepted": [.sign, .edit],
            "refused": [.edit],
            "withdrawn": [.edit],
            "paused": [.edit],
            "draft": [],
        ]
        for (state, expected) in table {
            #expect(actionsFor(page(state)) == expected, "\(state)")
        }
    }

    @Test func `sign is gone once signed`() {
        let signed = page("accepted", signedAt: "2026-11-04T09:00:00Z")
        #expect(!signable(signed))
        #expect(actionsFor(signed) == [.edit])
        #expect(signable(page("draft")))
        #expect(!signable(page("active")))
    }

    @Test func `the consent section stays through acceptance, signed or not`() {
        // Once saved, the section shows „Semnat” with the date instead of the pad (G7)
        for state in ["draft", "submitted", "accepted"] {
            #expect(showsConsent(page(state)), "\(state)")
            #expect(showsConsent(page(state, signedAt: "2026-11-04T09:00:00Z")), "\(state)")
        }
        for state in ["active", "wrong_number", "unreachable", "refused", "withdrawn", "x"] {
            #expect(!showsConsent(page(state)), "\(state)")
        }
    }

    @Test func `a card's sentence does not repeat its chip`() {
        #expect(says("wrong_number") == nil)
        #expect(says("unreachable") == nil)
        #expect(says("accepted") == "says_welcome_pending")
        #expect(says("active") == nil)
    }

    @Test func `stages for an active senior`() {
        let stages = stagesOf(
            page(
                "active", createdAt: "c", submittedAt: "s", acceptedAt: "a",
                consent: ConsentState(decision: "given", method: "call", at: "g"),
                consentGivenAt: "g"))
        #expect(
            stages.map(\.label) == [
                "stage_draft", "stage_submitted", "stage_accepted", "stage_active",
            ])
        #expect(stages.map(\.at) == ["c", "s", "a", "g"])
        #expect(stages.allSatisfy { $0.reached })
    }

    @Test func `stages for a withdrawal keep the active date`() {
        let stages = stagesOf(
            page(
                "withdrawn", createdAt: "c", submittedAt: "s", acceptedAt: "a",
                consent: ConsentState(decision: "withdrawn", method: "call", at: "w"),
                consentGivenAt: "g"))
        #expect(stages.count == 5)
        #expect(stages[3].at == "g")
        #expect(stages[4].label == "stage_withdrawn")
        #expect(stages[4].at == "w")
        #expect(stages.allSatisfy { $0.reached })
    }

    @Test func `a refusal reaches three stages then Refuzat`() {
        let stages = stagesOf(
            page("refused", consent: ConsentState(decision: "refused", method: "call", at: "r")))
        #expect(stages.map(\.reached) == [true, true, true, false, true])
        #expect(stages[4].label == "stage_refused")
        #expect(stages[4].at == "r")
    }

    @Test func `stages from an older API have no dates`() {
        let stages = stagesOf(page("accepted"))
        #expect(stages.map(\.reached) == [true, true, true, false])
        #expect(stages.allSatisfy { $0.at == nil })
        #expect(stagesOf(page("draft")).map(\.reached) == [true, false, false, false])
        #expect(stagesOf(page("paused")).count == 4)
        #expect(stagesOf(page("submitted")).map(\.reached) == [true, true, false, false])
    }

    @Test func `a failed call adds its end stage`() {
        let wrong = stagesOf(page("wrong_number"))
        #expect(wrong[4].label == "stage_wrong_number")
        #expect(wrong[4].at == nil)
        #expect(wrong[4].reached)
        #expect(stagesOf(page("unreachable"))[4].label == "stage_unreachable")
    }

    @Test func `a stage date is day and month in Romanian`() {
        let utc = TimeZone(identifier: "UTC")!
        let date = shortDate("2026-11-04T09:30:00Z", zone: utc)
        #expect(date.hasPrefix("4 nov"), "\(date)")
        #expect(shortDate("2026-11-04T09:30:00Z", zone: utc, year: true).hasSuffix("2026"))
    }

    @Test func `an unreadable date shows as sent`() {
        #expect(shortDate("ieri", zone: TimeZone(identifier: "UTC")!) == "ieri")
    }

    @Test func `a consent decision or method this build does not know has no label`() {
        #expect(CONSENT_DECISIONS["withdrawn"] == "consent_withdrawn")
        #expect(CONSENT_METHODS["das"] == "consent_das")
        #expect(CONSENT_METHODS["signature"] == nil)
    }
}
