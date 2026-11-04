package ro.echocare.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.Medic
import ro.echocare.SeniorPage

// UC-12, 04 §2: what the medic's „Sună din nou” and withdrawal answered.
class CommandsTest {
    private fun page(state: String, phone: String) = SeniorPage(
        id = "s",
        fullName = "S",
        formOfAddress = "Dna",
        phone = phone,
        landline = false,
        state = state,
        medic = Medic(displayName = "M")
    )

    @Test
    fun `200 is done`() {
        assertEquals(CommandOutcome.Done, commandOutcome(200, null))
    }

    @Test
    fun `409 wrong_state is refused with its reason`() {
        assertEquals(
            CommandOutcome.Refused("wrong_state"),
            commandOutcome(409, """{"detail":{"reason":"wrong_state"}}""")
        )
    }

    @Test
    fun `409 already_done is refused with its reason`() {
        assertEquals(
            CommandOutcome.Refused("already_done"),
            commandOutcome(409, """{"detail":{"reason":"already_done"}}""")
        )
    }

    @Test
    fun `403 and 404 are refused without a reason`() {
        assertEquals(CommandOutcome.Refused(null), commandOutcome(403, null))
        assertEquals(
            CommandOutcome.Refused(null),
            commandOutcome(404, """{"detail":{"reason":"not_found"}}""")
        )
    }

    @Test
    fun `no answer is offline`() {
        assertEquals(CommandOutcome.Offline, commandOutcome(null, null))
    }

    @Test
    fun `a 5xx is offline, as for a read`() {
        assertEquals(CommandOutcome.Offline, commandOutcome(503, "<html>Bad gateway</html>"))
    }

    @Test
    fun `a read that went through clears an offline notice, not a refusal`() {
        assertEquals(null, noticeAfterRead(CommandOutcome.Offline))
        assertEquals(
            CommandOutcome.Refused("wrong_state"),
            noticeAfterRead(CommandOutcome.Refused("wrong_state"))
        )
        assertEquals(null, noticeAfterRead(null))
    }

    @Test
    fun `a new number on a senior to resolve is a changed number`() {
        assertTrue(numberChanged("+40700000001", page("wrong_number", "+40700000002")))
        assertTrue(numberChanged("+40700000001", page("unreachable", "+40700000002")))
    }

    @Test
    fun `the same number, or a senior not to resolve, is not`() {
        assertFalse(numberChanged("+40700000001", page("unreachable", "+40700000001")))
        assertFalse(numberChanged("+40700000001", page("active", "+40700000002")))
    }
}
