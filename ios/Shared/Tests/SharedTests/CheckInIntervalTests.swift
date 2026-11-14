import Testing
@testable import Shared

// 06 §3: a check-in every 15 minutes, every minute in the demo (Wear OS CHECK_IN_MINUTES).
struct CheckInIntervalTests {
    @Test("the demo checks in every minute")
    func demo() {
        #expect(CheckInInterval.minutes(demo: true) == 1)
        #expect(CheckInInterval.seconds(demo: true) == 60)
    }

    @Test("production checks in every 15 minutes")
    func production() {
        #expect(CheckInInterval.minutes(demo: false) == 15)
        #expect(CheckInInterval.seconds(demo: false) == 900)
    }
}
