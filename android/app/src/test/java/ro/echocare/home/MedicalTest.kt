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
    fun `pending analyzes once the senior is accepted or active`() {
        assertEquals(MedicalStage.Analyzing, stageOf(record("pending"), "accepted"))
        assertEquals(MedicalStage.Analyzing, stageOf(record("pending"), "active"))
    }

    @Test
    fun `pending is never analyzed for a senior the server does not analyze`() {
        for (state in listOf("refused", "withdrawn", "wrong_number", "unreachable", "new_state")) {
            assertEquals(MedicalStage.NotAnalyzed, stageOf(record("pending"), state))
        }
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
        val edited = listOf(item("  a  "), item(" b", included = false), item("c "))
        val form = confirmFormOf(edited, edited)
        assertEquals(listOf("a", "b", "c"), form.items.map { it.question })
        assertEquals(listOf(true, false, true), form.items.map { it.included })
    }

    @Test
    fun `a blanked excluded item sends its stored question`() {
        val stored = listOf(item("a"), item("kept", included = false))
        val edited = listOf(item(" a2 "), item("  ", included = false))
        assertEquals(listOf("a2", "kept"), confirmFormOf(edited, stored).items.map { it.question })
    }

    @Test
    fun `a reread with fewer stored items does not crash the confirm form`() {
        val edited = listOf(item("a"), item("  ", included = false))
        val form = confirmFormOf(edited, stored = listOf(item("a")))
        assertEquals(listOf("a", ""), form.items.map { it.question })
    }

    @Test
    fun `reanalyzing a confirmed profile waits for Modifica`() {
        assertFalse(canReanalyze(MedicalStage.Confirmed, editing = false))
        assertTrue(canReanalyze(MedicalStage.Confirmed, editing = true))
        assertTrue(canReanalyze(MedicalStage.Review, editing = false))
        assertTrue(canReanalyze(MedicalStage.Failed, editing = false))
        assertFalse(canReanalyze(MedicalStage.Analyzing, editing = false))
    }

    @Test
    fun `an included blank question blocks confirming`() {
        assertFalse(canConfirm(listOf(item("a"), item("  "))))
        assertTrue(canConfirm(listOf(item("a"), item("", included = false))))
    }
}
