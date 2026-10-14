package bia.sentinela.home

import bia.sentinela.R
import bia.sentinela.auth.ROLES
import bia.sentinela.ui.Tone
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

// seniors §8.2: which home each role gets.
class RoutesTest {
    @Test
    fun eachRoleHasItsHome() {
        assertEquals(SeniorsRoute("medic"), homeFor("medic"))
        assertEquals(SeniorsRoute("caregiver"), homeFor("caregiver"))
        assertEquals(OwnRoute, homeFor("senior"))
        assertEquals(IncidentsRoute, homeFor("das"))
    }

    @Test
    fun everyRoleTheAppKnowsHasAHome() {
        // Four roles, three kinds of home: the medic and the caregiver share the list.
        assertEquals(4, ROLES.map(::homeFor).toSet().size)
    }

    @Test
    fun everyStateOfTheDataModelHasALabel() {
        // 05 §1, in order.
        val states = listOf(
            "draft",
            "submitted",
            "accepted",
            "active",
            "refused",
            "wrong_number",
            "unreachable"
        )
        assertEquals(states, STATE_LABELS.keys.toList())
        assertEquals(R.string.state_draft, STATE_LABELS["draft"])
        assertEquals(states.size, STATE_LABELS.values.toSet().size)
    }

    @Test
    fun aStateThisBuildDoesNotKnowHasNoLabel() {
        assertNull(STATE_LABELS["paused"])
    }

    @Test
    fun everyLabelledStateHasTheDashboardsColour() {
        assertEquals(STATE_LABELS.keys, STATE_TONES.keys)
        assertEquals(Tone.Verde, STATE_TONES["active"])
        assertEquals(Tone.Galben, STATE_TONES["unreachable"])
    }
}
