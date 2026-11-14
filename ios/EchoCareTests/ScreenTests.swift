import Testing

@testable import EchoCare

// auth-layer §8.2: what the app does with each answer from /me. Ported from Android's ScreenTest.kt.
struct ScreenTests {
    private func me(_ roles: String...) -> Me {
        Me(displayName: "Ana Pop", grants: roles.map { Grant(role: $0) })
    }

    @Test func oneDistinctRoleOpensHome() {
        #expect(
            screenFor(me("caregiver", "caregiver"), saved: nil)
                == .home(role: "caregiver", displayName: "Ana Pop", roles: ["caregiver"]))
        #expect(
            screenFor(me("das"), saved: "medic")
                == .home(role: "das", displayName: "Ana Pop", roles: ["das"]))
    }

    @Test func severalRolesWithValidSavedRoleOpensIt() {
        #expect(
            screenFor(me("das", "medic"), saved: "medic")
                == .home(role: "medic", displayName: "Ana Pop", roles: ["das", "medic"]))
    }

    @Test func homeListsEveryKnownRoleInOrder() {
        // The profile page lists them to switch between (design 2026-11-13 medic home)
        let home = screenFor(me("caregiver", "medic", "das", "pilot", "medic"), saved: "medic")
        #expect(home == .home(role: "medic", displayName: "Ana Pop", roles: ["das", "medic", "caregiver"]))
        #expect(home.canSwitch)
        #expect(!Screen.home(role: "das", displayName: "Ana Pop", roles: ["das"]).canSwitch)
    }

    @Test func severalRolesWithoutValidSavedRolePicks() {
        #expect(screenFor(me("das", "medic"), saved: nil) == .pickRole(["das", "medic"]))
        #expect(screenFor(me("das", "medic"), saved: "senior") == .pickRole(["das", "medic"]))
    }

    // Review Focus 3: a role this build doesn't know is dropped, never a failed screen.
    @Test func unknownRolesAreDropped() {
        #expect(
            screenFor(me("das", "nurse"), saved: nil)
                == .home(role: "das", displayName: "Ana Pop", roles: ["das"]))
        #expect(
            screenFor(me("das", "pilot"), saved: nil)
                == .home(role: "das", displayName: "Ana Pop", roles: ["das"]))
        #expect(screenFor(me("nurse"), saved: nil) == .notRegistered)
    }

    @Test func refusals() {
        #expect(screenFor(status: 401) == .phone())
        #expect(screenFor(status: 403) == .notRegistered)
        #expect(screenFor(status: 503) == .unavailable)
        #expect(screenFor(status: 500) == .unavailable)
    }

    @Test func phoneToE164() {
        #expect(toE164("0722 123 456") == "+40722123456")
        #expect(toE164("(0722) 123-456") == "+40722123456")
        #expect(toE164("0040.722.123.456") == "+40722123456")
        #expect(toE164("722123456") == "+40722123456")
        #expect(toE164("+40700000001") == "+40700000001")
        #expect(toE164("+1 650 555 0101") == "+16505550101")
    }
}
