package ro.echocare.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import ro.echocare.R
import ro.echocare.auth.ROLES
import ro.echocare.ui.Tone

// seniors §8.2: which home each role gets.
class RoutesTest {
    @Test
    fun eachRoleHasItsHome() {
        assertEquals(MedicHomeRoute, homeFor("medic"))
        assertEquals(SeniorsRoute("caregiver"), homeFor("caregiver"))
        assertEquals(OwnRoute, homeFor("senior"))
        assertEquals(IncidentsRoute, homeFor("das"))
    }

    @Test
    fun theMedicLandsOnTheMedicHome() {
        // UC-12: the medic's home is the two tiles, not the list
        assertEquals(MedicHomeRoute, homeFor("medic"))
    }

    @Test
    fun theCaregiverStillLandsOnTheirSeniors() {
        assertEquals(SeniorsRoute("caregiver"), homeFor("caregiver"))
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
            "unreachable",
            "withdrawn"
        )
        assertEquals(states, STATE_LABELS.keys.toList())
        assertEquals(R.string.state_draft, STATE_LABELS["draft"])
        assertEquals(states.size, STATE_LABELS.values.toSet().size)
    }

    @Test
    fun everyCallStateHasALabel() {
        // 05 §1's call states, worded as the dashboard's incident page
        val states = listOf(
            "queued",
            "ringing",
            "in_progress",
            "unanswered",
            "failed",
            "completed",
            "handed_over",
            "dropped",
            "canceled"
        )
        assertEquals(states, CALL_STATE_LABELS.keys.toList())
        assertEquals(states.size, CALL_STATE_LABELS.values.toSet().size)
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

    @Test
    fun withdrawnHasALabel() {
        // 05 §1: a withdrawn consent is a state of its own.
        assertEquals(R.string.state_withdrawn, STATE_LABELS["withdrawn"])
        assertEquals(Tone.Muted, STATE_TONES["withdrawn"])
    }

    @Test
    fun everyCodeHasALabelAndATone() {
        // 03 §8: green, yellow, red.
        val codes = setOf("green", "yellow", "red")
        assertEquals(codes, CODE_LABELS.keys)
        assertEquals(codes, CODE_TONES.keys)
    }
}
