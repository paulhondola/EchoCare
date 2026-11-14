import Testing

@testable import EchoCare

// seniors §8.2: which home each role gets. Ported from Android's home/RoutesTest.kt. Swift's
// dictionaries have no order, so the "in order" cases compare the keys as sets.
struct RoutesTests {
    @Test func eachRoleHasItsHome() {
        #expect(homeFor("medic") == .medicHome)
        #expect(homeFor("caregiver") == .seniors(role: "caregiver"))
        #expect(homeFor("senior") == .own)
        #expect(homeFor("das") == .incidents)
    }

    @Test func theMedicLandsOnTheMedicHome() {
        // UC-12: the medic's home is the two tiles, not the list
        #expect(homeFor("medic") == .medicHome)
    }

    @Test func theCaregiverStillLandsOnTheirSeniors() {
        #expect(homeFor("caregiver") == .seniors(role: "caregiver"))
    }

    @Test func everyRoleTheAppKnowsHasAHome() {
        // Four roles, three kinds of home: the medic and the caregiver share the list.
        #expect(Set(roles.map(homeFor)).count == 4)
    }

    @Test func everyStateOfTheDataModelHasALabel() {
        // 05 §1
        let states: Set = [
            "draft", "submitted", "accepted", "active", "refused", "wrong_number", "unreachable", "withdrawn",
        ]
        #expect(Set(STATE_LABELS.keys) == states)
        #expect(STATE_LABELS["draft"] == "state_draft")
        #expect(Set(STATE_LABELS.values).count == states.count)
    }

    @Test func everyCallStateHasALabel() {
        // 05 §1's call states, worded as the dashboard's incident page
        let states: Set = [
            "queued", "ringing", "in_progress", "unanswered", "failed", "completed", "handed_over", "dropped",
            "canceled",
        ]
        #expect(Set(CALL_STATE_LABELS.keys) == states)
        #expect(Set(CALL_STATE_LABELS.values).count == states.count)
    }

    @Test func aStateThisBuildDoesNotKnowHasNoLabel() {
        #expect(STATE_LABELS["paused"] == nil)
    }

    @Test func everyLabelledStateHasTheDashboardsColour() {
        #expect(Set(STATE_LABELS.keys) == Set(STATE_TONES.keys))
        #expect(STATE_TONES["active"] == .verde)
        #expect(STATE_TONES["unreachable"] == .galben)
    }

    @Test func withdrawnHasALabel() {
        // 05 §1: a withdrawn consent is a state of its own.
        #expect(STATE_LABELS["withdrawn"] == "state_withdrawn")
        #expect(STATE_TONES["withdrawn"] == .muted)
    }

    @Test func everyCodeHasALabelAndATone() {
        // 03 §8: green, yellow, red.
        let codes: Set = ["green", "yellow", "red"]
        #expect(Set(CODE_LABELS.keys) == codes)
        #expect(Set(CODE_TONES.keys) == codes)
    }
}
