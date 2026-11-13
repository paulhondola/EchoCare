package ro.echocare.auth

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.Grant
import ro.echocare.Me

// auth-layer §8.2: what the app does with each answer from /me.
class ScreenTest {
    private fun me(vararg roles: String) = Me("Ana Pop", roles.map(::Grant))

    @Test
    fun oneDistinctRoleOpensHome() {
        assertEquals(
            Screen.Home("caregiver", "Ana Pop", listOf("caregiver")),
            screenFor(me("caregiver", "caregiver"), null)
        )
        assertEquals(
            Screen.Home("das", "Ana Pop", listOf("das")),
            screenFor(me("das"), "medic")
        )
    }

    @Test
    fun severalRolesWithValidSavedRoleOpensIt() {
        assertEquals(
            Screen.Home("medic", "Ana Pop", listOf("das", "medic")),
            screenFor(me("das", "medic"), "medic")
        )
    }

    @Test
    fun homeListsEveryKnownRoleInOrder() {
        // The profile page lists them to switch between (design 2026-11-13 medic home)
        val home = screenFor(me("caregiver", "medic", "das", "pilot", "medic"), "medic")
        assertEquals(Screen.Home("medic", "Ana Pop", listOf("das", "medic", "caregiver")), home)
        assertTrue((home as Screen.Home).canSwitch)
        assertFalse(Screen.Home("das", "Ana Pop", listOf("das")).canSwitch)
    }

    @Test
    fun severalRolesWithoutValidSavedRolePicks() {
        assertEquals(Screen.PickRole(listOf("das", "medic")), screenFor(me("das", "medic"), null))
        assertEquals(
            Screen.PickRole(listOf("das", "medic")),
            screenFor(me("das", "medic"), "senior")
        )
    }

    @Test
    fun unknownRolesAreDropped() {
        assertEquals(
            Screen.Home("das", "Ana Pop", listOf("das")),
            screenFor(me("das", "nurse"), null)
        )
        assertEquals(Screen.NotRegistered, screenFor(me("nurse"), null))
    }

    @Test
    fun refusals() {
        assertEquals(Screen.Phone(), screenFor(401))
        assertEquals(Screen.NotRegistered, screenFor(403))
        assertEquals(Screen.Unavailable, screenFor(503))
        assertEquals(Screen.Unavailable, screenFor(500))
    }

    @Test
    fun phoneToE164() {
        assertEquals("+40722123456", toE164("0722 123 456"))
        assertEquals("+40722123456", toE164("(0722) 123-456"))
        assertEquals("+40722123456", toE164("0040.722.123.456"))
        assertEquals("+40722123456", toE164("722123456"))
        assertEquals("+40700000001", toE164("+40700000001"))
        assertEquals("+16505550101", toE164("+1 650 555 0101"))
    }
}
