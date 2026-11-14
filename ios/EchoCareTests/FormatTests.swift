import Testing

@testable import EchoCare

// Ported from Android's ui/FormatTest.kt, case for case: the same cases as the dashboard's
// phone.test.ts, so every client shows a number alike.
struct FormatTests {
    @Test func romanianNumbersAreGroupedAsPeopleReadThem() {
        #expect(formatPhone("+40722111222") == "0722 111 222")
        #expect(formatPhone("+40214567788") == "021 456 7788")
        #expect(formatPhone("+40264123456") == "0264 123 456")
    }

    @Test func otherNumbersStayAsTheyAre() {
        #expect(formatPhone("+16505550101") == "+16505550101")
        #expect(formatPhone("+4072") == "+4072")
    }

    @Test func initialsAreTheFirstAndLastWordsLettersWithoutTitles() {
        #expect(initials("Dr. Ana Ionescu") == "AI")
        #expect(initials("Maria") == "M")
        #expect(initials("ana maria pop") == "AP")
        #expect(initials("  ") == "")
        #expect(initials("Dr.") == "")
    }
}
