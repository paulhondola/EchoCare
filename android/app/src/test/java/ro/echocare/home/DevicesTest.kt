package ro.echocare.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.Medic
import ro.echocare.R
import ro.echocare.RoomInfo
import ro.echocare.SeniorPage

// UC-13, design 2026-11-14: which devices a senior's page shows and what it warns about.
class DevicesTest {
    private val page = SeniorPage(
        id = "s1",
        fullName = "Maria Popescu",
        formOfAddress = "doamna Maria",
        phone = "+40700000005",
        landline = false,
        state = "active",
        medic = Medic("Dr. Ion Pop"),
        equipment = listOf("smartphone", "watch"),
        appSignedIn = false
    )

    @Test
    fun theWatchHidesOnlyWhenTheEquipmentSaysThereIsNone() {
        assertTrue(showsWatch(page.copy(equipment = null)))
        assertTrue(showsWatch(page))
        assertFalse(showsWatch(page.copy(equipment = emptyList())))
        assertFalse(showsWatch(page.copy(equipment = listOf("smartphone"))))
    }

    @Test
    fun aDeclaredWatchWithNoDataAndAnUnopenedAppBothWarn() {
        assertEquals(
            listOf(R.string.device_watch_never, R.string.device_app_never),
            deviceWarnings(page, forSenior = false)
        )
    }

    @Test
    fun theWarningsStopOnceTheWatchReportsAndTheAppIsOpened() {
        val reporting = page.copy(watchState = "ok", appSignedIn = true)
        assertEquals(emptyList<Int>(), deviceWarnings(reporting, forSenior = false))
    }

    @Test
    fun aDeclaredHomeNodeWarnsUntilItsFirstRoomReading() {
        val node = page.copy(equipment = listOf("smartphone", "home_node"), appSignedIn = true)
        assertEquals(listOf(R.string.device_node_never), deviceWarnings(node, forSenior = false))
        val reporting = node.copy(room = RoomInfo(temperature = 21.5))
        assertEquals(emptyList<Int>(), deviceWarnings(reporting, forSenior = false))
    }

    @Test
    fun noWarningsWhenNotStatedBeforeAcceptanceFromAnOlderApiOrForTheSenior() {
        assertEquals(emptyList<Int>(), deviceWarnings(page.copy(equipment = null), false))
        assertEquals(emptyList<Int>(), deviceWarnings(page.copy(state = "submitted"), false))
        assertEquals(2, deviceWarnings(page.copy(state = "accepted"), false).size)
        val olderApi = page.copy(watchState = "ok", appSignedIn = null)
        assertEquals(emptyList<Int>(), deviceWarnings(olderApi, false))
        assertEquals(emptyList<Int>(), deviceWarnings(page, forSenior = true))
    }
}
