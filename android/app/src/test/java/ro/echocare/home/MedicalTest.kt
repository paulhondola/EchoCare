package ro.echocare.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.MedicalItem
import ro.echocare.MedicalRecord

// Design §5.7: the medic's medical record section.
class MedicalTest {
    private fun record(state: String) =
        MedicalRecord(state = state, uploadedAt = "2026-11-13T10:00:00Z")

    private fun item(question: String, included: Boolean = true) =
        MedicalItem("c", question, "w", included = included)

    @Test
    fun `no record is none`() {
        assertEquals(MedicalStage.None, stageOf(null, "active"))
    }

    @Test
    fun `pending waits for DAS while the senior is a draft or submitted`() {
        assertEquals(MedicalStage.WaitingForDas, stageOf(record("pending"), "draft"))
        assertEquals(MedicalStage.WaitingForDas, stageOf(record("pending"), "submitted"))
    }

    @Test
    fun `pending analyzes once the senior is further on`() {
        assertEquals(MedicalStage.Analyzing, stageOf(record("pending"), "active"))
    }

    @Test
    fun `review, confirmed and failed`() {
        assertEquals(MedicalStage.Review, stageOf(record("review"), "active"))
        assertEquals(MedicalStage.Confirmed, stageOf(record("confirmed"), "active"))
        assertEquals(MedicalStage.Failed, stageOf(record("failed"), "active"))
    }

    @Test
    fun `an unknown state is analyzing`() {
        assertEquals(MedicalStage.Analyzing, stageOf(record("something_new"), "active"))
    }

    @Test
    fun `the confirm form trims, keeps order and included`() {
        val form = confirmFormOf(listOf(item("  a  "), item(" b", included = false), item("c ")))
        assertEquals(listOf("a", "b", "c"), form.items.map { it.question })
        assertEquals(listOf(true, false, true), form.items.map { it.included })
    }

    @Test
    fun `an included blank question blocks confirming`() {
        assertFalse(canConfirm(listOf(item("a"), item("  "))))
        assertTrue(canConfirm(listOf(item("a"), item("", included = false))))
    }
}
