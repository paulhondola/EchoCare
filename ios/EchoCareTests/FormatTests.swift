import Testing

@testable import EchoCare

// The two helpers the top bar and the profile page need, ported from Android's ui/FormatTest.kt.
// Task 9 ports the rest of that file.
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
