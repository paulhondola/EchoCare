package ro.echocare.push

import java.io.IOException
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.home.IncidentRoute
import ro.echocare.home.SeniorRoute
import ro.echocare.home.alertRoute

// 04 §6: what a push says, and where a tapped alert goes.
class PushTest {
    @Test
    fun aCodeAlertNamesItsSenior() {
        assertEquals(
            Push.Alert("s1", null),
            pushFrom(mapOf("type" to "code_changed", "senior_id" to "s1"))
        )
    }

    @Test
    fun anIncidentAlertNamesItsIncidentToo() {
        assertEquals(
            Push.Alert("s1", "i1"),
            pushFrom(mapOf("type" to "incident", "senior_id" to "s1", "incident_id" to "i1"))
        )
    }

    @Test
    fun aRefreshIsARefresh() {
        assertEquals(
            Push.Refresh,
            pushFrom(mapOf("type" to "refresh", "what" to "senior", "senior_id" to "s1"))
        )
    }

    @Test
    fun aTypeThisBuildDoesNotKnowIsARefresh() {
        // ADR-001 §2.3: the server may add types before every phone has updated
        assertEquals(Push.Refresh, pushFrom(mapOf("type" to "watch_silent", "senior_id" to "s1")))
    }

    @Test
    fun anAlertWithoutItsSeniorOnlyRefreshes() {
        assertEquals(Push.Refresh, pushFrom(mapOf("type" to "code_changed")))
    }

    @Test
    fun aLauncherTapIsNoPush() {
        assertNull(pushFrom(mapOf("type" to null, "senior_id" to null)))
    }

    @Test
    fun aTokenIsSavedBeforeTheServiceMayStop() {
        // The service stops once onNewToken returns, so the save has to end first
        var saved = false
        saveBeforeReturning {
            delay(50)
            saved = true
        }
        assertTrue(saved)
    }

    @Test
    fun aSaveThatFailsOfflineIsLeftForTheNextStart() {
        saveBeforeReturning { throw IOException("offline") }
    }

    @Test
    fun aSaveThatHangsLetsTheNextMessageThrough() {
        // Messages wait on the same thread as onNewToken: an alert must not wait for ever
        var finished = false
        saveBeforeReturning(limit = 50.milliseconds) {
            delay(10.seconds)
            finished = true
        }
        assertFalse(finished)
    }

    @Test
    fun theCaregiverAndTheMedicOpenTheSeniorsPage() {
        assertEquals(SeniorRoute("s1"), alertRoute("s1", null, "caregiver"))
        assertEquals(SeniorRoute("s1"), alertRoute("s1", null, "medic"))
    }

    @Test
    fun dasOpensTheIncident() {
        assertEquals(IncidentRoute("i1"), alertRoute("s1", "i1", "das"))
    }

    @Test
    fun aCodeAlertOpensTheSeniorInTheDasRole() {
        // Someone who is also a caregiver: the alert is about their senior, and a tap must open it
        assertEquals(SeniorRoute("s1"), alertRoute("s1", null, "das"))
    }

    @Test
    fun anAlertOpensTheSeniorInTheSeniorRole() {
        // A senior who also cares for someone: their own home is not the page the alert is about
        assertEquals(SeniorRoute("s2"), alertRoute("s2", null, "senior"))
    }

    @Test
    fun aBurstOfRefreshesIsOneRead() = runBlocking {
        // One commit can push several refreshes, and each read asks for a whole page and its calls
        var reads = 0
        val reader = launch { Refreshes.events.collect { reads++ } }
        delay(100)
        repeat(3) {
            Refreshes.signal()
            delay(50)
        }
        delay(1.seconds)
        reader.cancel()
        assertEquals(1, reads)
    }

    @Test
    fun anIncidentAlertOpensTheSeniorForAMedicWhoIsAlsoDas() {
        // The app is in the medic role: the medic's page, not a DAS screen
        assertEquals(SeniorRoute("s1"), alertRoute("s1", "i1", "medic"))
    }
}
