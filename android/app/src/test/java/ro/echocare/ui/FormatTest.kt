package ro.echocare.ui

import org.junit.Assert.assertEquals
import org.junit.Test

// The same cases as the dashboard's phone.test.ts, so both clients show a number alike.
class FormatTest {
    @Test
    fun romanianNumbersAreGroupedAsPeopleReadThem() {
        assertEquals("0722 111 222", formatPhone("+40722111222"))
        assertEquals("021 456 7788", formatPhone("+40214567788"))
        assertEquals("0264 123 456", formatPhone("+40264123456"))
    }

    @Test
    fun otherNumbersStayAsTheyAre() {
        assertEquals("+16505550101", formatPhone("+16505550101"))
        assertEquals("+4072", formatPhone("+4072"))
    }

    @Test
    fun initialsAreTheFirstAndLastWordsLettersWithoutTitles() {
        assertEquals("AI", initials("Dr. Ana Ionescu"))
        assertEquals("M", initials("Maria"))
        assertEquals("AP", initials("ana maria pop"))
        assertEquals("", initials("  "))
    }
}
