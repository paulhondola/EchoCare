import Foundation
import Testing

@testable import EchoCare

// UC-12: what the caregiver's page shows for each code and each call. Ported from Android's
// home/CallsTest.kt.
struct CallsTests {
    private func call(
        state: String = "completed", severity: String? = nil, due: String = "2026-11-04T08:00:00Z",
        started: String? = nil, ended: String? = nil
    ) -> CallRow {
        CallRow(
            id: "c", trigger: "campaign", state: state, dueAt: due, startedAt: started,
            endedAt: ended,
            finalSeverity: severity)
    }

    private func senior(code: String?, live: Bool?) -> SeniorPage {
        SeniorPage(
            id: "s", fullName: "Maria Pop", formOfAddress: "doamna Maria", phone: "+40700000101",
            landline: false, state: "active", code: code, reason: "Se simte rău",
            medic: Medic(displayName: "Dr. Pop"), callInProgress: live)
    }

    @Test func eachCodeHasItsLabelAndColour() {
        #expect(CODE_LABELS["green"] == "code_green")
        #expect(CODE_LABELS["yellow"] == "code_yellow")
        #expect(CODE_LABELS["red"] == "code_red")
        #expect(CODE_TONES["green"] == .verde)
        #expect(CODE_TONES["yellow"] == .galben)
        #expect(CODE_TONES["red"] == .rosu)
    }

    @Test func noCodeOrAnUnknownOneShowsNoChip() {
        // Nil before the first result and for a senior not active (04 §1)
        #expect(senior(code: nil, live: nil).code.flatMap { CODE_LABELS[$0] } == nil)
        #expect(CODE_LABELS["purple"] == nil)
    }

    @Test func aWatchThatIsNotWatchingIsAWarning() {
        // UC-13: a device warning beside the senior, not a code
        #expect(watchChip("not_worn")?.label == "watch_not_worn")
        #expect(watchChip("not_worn")?.tone == .galben)
        #expect(watchChip("offline")?.label == "watch_offline")
        #expect(watchChip("offline")?.tone == .galben)
    }

    @Test func aWatchThatWorksIsNoWarning() {
        #expect(watchChip("ok")?.label == "watch_ok")
        #expect(watchChip("ok")?.tone == .muted)
    }

    @Test func noWatchOrAnUnknownStateShowsNoChip() {
        // Nil for DAS and the senior, and before the first check-in (04 §1)
        #expect(watchChip(nil) == nil)
        #expect(watchChip("charging") == nil)
    }

    @Test func anEndedCallShowsItsCode() {
        for code in ["green", "yellow", "red"] {
            #expect(outcome(call(severity: code)) == .code(code))
        }
    }

    @Test func aCallWithoutACodeShowsItsState() {
        #expect(outcome(call(state: "queued")) == .state("queued"))
        #expect(outcome(call(state: "ringing")) == .state("ringing"))
        #expect(outcome(call(state: "failed")) == .state("failed"))
    }

    @Test func aCodeThisBuildDoesNotKnowShowsTheState() {
        #expect(outcome(call(severity: "purple")) == .state("completed"))
    }

    @Test func aLiveCallStandsOut() {
        #expect(stateTone("ringing") == .galben)
        #expect(stateTone("in_progress") == .galben)
        #expect(stateTone("queued") == .muted)
        #expect(stateTone("unanswered") == .muted)
    }

    @Test func theHistoryIsShortAndLeavesOutCanceledCalls() {
        let calls = [call(state: "canceled")] + Array(repeating: call(), count: 7)
        let recent = recentCalls(calls)
        #expect(recent.count == RECENT_CALLS)
        #expect(!recent.contains { $0.state == "canceled" })
    }

    @Test func aCallIsTimedByItsEndThenItsStartThenWhenItIsDue() {
        let utc = TimeZone(identifier: "UTC")!
        #expect(callTime(call(), zone: utc) == "04.11 08:00")
        #expect(callTime(call(started: "2026-11-04T08:01:00Z"), zone: utc) == "04.11 08:01")
        #expect(
            callTime(
                call(started: "2026-11-04T08:01:00Z", ended: "2026-11-04T08:05:00Z"), zone: utc)
                == "04.11 08:05")
        // In the phone's zone: Bucharest is UTC+2 in November
        #expect(callTime(call(), zone: TimeZone(identifier: "Europe/Bucharest")!) == "04.11 10:00")
    }

    @Test func theBadgeShowsOnlyWhileACallIsLive() {
        #expect(showsCallBadge(senior(code: "yellow", live: true)))
        #expect(!showsCallBadge(senior(code: "yellow", live: false)))
        // An older API that does not send the field
        #expect(!showsCallBadge(senior(code: "yellow", live: nil)))
    }

    // UC-13, design 2026-11-14: which devices a senior's page shows and what it warns about.
    private func devices(
        _ equipment: [String]? = ["smartphone", "watch"], state: String = "active",
        watch: String? = nil, signedIn: Bool? = false
    ) -> SeniorPage {
        var page = SeniorPage(
            id: "s1", fullName: "Maria Popescu", formOfAddress: "doamna Maria",
            phone: "+40700000005", landline: false, state: state,
            medic: Medic(displayName: "Dr. Ion Pop"), watchState: watch)
        page.equipment = equipment
        page.appSignedIn = signedIn
        return page
    }

    @Test func `the watch hides only when the equipment says there is none`() {
        #expect(showsWatch(devices(nil)))
        #expect(showsWatch(devices()))
        #expect(!showsWatch(devices([])))
        #expect(!showsWatch(devices(["smartphone"])))
    }

    @Test func `a declared watch with no data and an unopened app both warn`() {
        #expect(
            deviceWarnings(devices(), forSenior: false) == [
                "device_watch_never", "device_app_never",
            ])
    }

    @Test func `the warnings stop once the watch reports and the app is opened`() {
        #expect(deviceWarnings(devices(watch: "ok", signedIn: true), forSenior: false) == [])
    }

    @Test func `a declared home node warns until its first room reading`() {
        var node = devices(["smartphone", "home_node"], signedIn: true)
        #expect(deviceWarnings(node, forSenior: false) == ["device_node_never"])
        node.hasRoom = true
        #expect(deviceWarnings(node, forSenior: false) == [])
    }

    @Test func `a room reading in the page is noticed`() throws {
        func page(_ room: String) throws -> SeniorPage {
            let json = """
                {"id":"s1","full_name":"M","form_of_address":"d","phone_e164":"+40700000005",
                 "phone_is_landline":false,"enrollment_state":"active",
                 "medic":{"display_name":"D"}\(room)}
                """
            return try ApiClient.makeDecoder().decode(SeniorPage.self, from: Data(json.utf8))
        }
        #expect(try page(#","room":{"state":"ok","temperature":21.5,"room_state":"ok"}"#).hasRoom)
        #expect(try !page(#","room":null"#).hasRoom)
        #expect(try !page("").hasRoom)
    }

    @Test
    func `no warnings when not stated, before acceptance, from an older API or for the senior`() {
        #expect(deviceWarnings(devices(nil), forSenior: false) == [])
        #expect(deviceWarnings(devices(state: "submitted"), forSenior: false) == [])
        #expect(deviceWarnings(devices(state: "accepted"), forSenior: false).count == 2)
        #expect(deviceWarnings(devices(watch: "ok", signedIn: nil), forSenior: false) == [])
        #expect(deviceWarnings(devices(), forSenior: true) == [])
    }
}
