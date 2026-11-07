package ro.echocare.home

import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.ConsentState
import ro.echocare.Medic
import ro.echocare.R
import ro.echocare.SeniorPage
import ro.echocare.SeniorRow

// UC-12, 03 §7: the medic's panel groups, actions and the enrollment stages.
class PanelTest {
    private fun row(id: String, state: String, code: String? = null, since: String? = null) =
        SeniorRow(
            id = id,
            fullName = id,
            formOfAddress = "Dna",
            phone = "+40700000000",
            landline = false,
            state = state,
            code = code,
            since = since
        )

    private fun page(
        state: String,
        signedAt: String? = null,
        createdAt: String? = null,
        submittedAt: String? = null,
        acceptedAt: String? = null,
        consent: ConsentState? = null,
        consentGivenAt: String? = null
    ) = SeniorPage(
        id = "s", fullName = "S", formOfAddress = "Dna", phone = "+40700000000", landline = false,
        state = state, medic = Medic(displayName = "M"),
        createdAt = createdAt, submittedAt = submittedAt, acceptedAt = acceptedAt,
        consent = consent, consentGivenAt = consentGivenAt, signedAt = signedAt
    )

    @Test
    fun `a red is above a yellow is above everything`() {
        val rows = listOf(
            row("g", "active", "green"),
            row("y", "active", "yellow"),
            row("r", "active", "red")
        )
        val first = panel(rows).first()
        assertEquals(Group.Urgent, first.first)
        assertEquals(listOf("r", "y"), first.second.map { it.id })
    }

    @Test
    fun `the oldest red first`() {
        val rows = listOf(
            row("none", "active", "red", null),
            row("new", "active", "red", "2026-11-04T10:00:00Z"),
            row("old", "active", "red", "2026-11-04T08:00:00Z")
        )
        assertEquals(listOf("old", "new", "none"), panel(rows).first().second.map { it.id })
    }

    @Test
    fun `groups come in order and empty ones go`() {
        val rows = listOf(
            row("a", "refused"),
            row("b", "submitted"),
            row("c", "active", "green"),
            row("d", "accepted"),
            row("e", "wrong_number"),
            row("f", "active", "red"),
            row("g", "draft")
        )
        assertEquals(
            listOf(
                Group.Urgent,
                Group.ToResolve,
                Group.InProgress,
                Group.Green,
                Group.AtDas,
                Group.Inactive
            ),
            panel(rows).map { it.first }
        )
        assertTrue(panel(rows).flatMap { it.second }.none { it.id == "g" })
    }

    @Test
    fun `an unknown state is inactive`() {
        assertEquals(Group.Inactive, groupOf(row("x", "paused")))
        assertEquals(Group.Inactive, groupOf(row("w", "withdrawn")))
    }

    @Test
    fun `active without a code is green`() {
        assertEquals(Group.Green, groupOf(row("x", "active")))
        assertEquals(Group.Green, groupOf(row("x", "active", "mystery")))
        assertEquals(null, groupOf(row("x", "draft")))
    }

    @Test
    fun `counts`() {
        val rows = listOf(
            row("1", "active", "red"),
            row("2", "active", "yellow"),
            row("3", "active", "yellow"),
            row("4", "wrong_number"),
            row("5", "unreachable"),
            row("6", "draft"),
            row("7", "active", "green")
        )
        assertEquals(Counts(red = 1, yellow = 2, toResolve = 2, drafts = 1), countsOf(rows))
    }

    @Test
    fun `actions by state`() {
        val table = mapOf(
            "wrong_number" to listOf(PatientAction.CallAgain, PatientAction.Edit),
            "unreachable" to listOf(PatientAction.CallAgain, PatientAction.Edit),
            "active" to listOf(PatientAction.Withdraw, PatientAction.Edit),
            "submitted" to listOf(PatientAction.Sign, PatientAction.Edit),
            "accepted" to listOf(PatientAction.Sign, PatientAction.Edit),
            "refused" to listOf(PatientAction.Edit),
            "withdrawn" to listOf(PatientAction.Edit),
            "paused" to listOf(PatientAction.Edit),
            "draft" to emptyList()
        )
        for ((state, expected) in table) assertEquals(state, expected, actionsFor(page(state)))
    }

    @Test
    fun `sign is gone once signed`() {
        val signed = page("accepted", signedAt = "2026-11-04T09:00:00Z")
        assertFalse(signable(signed))
        assertEquals(listOf(PatientAction.Edit), actionsFor(signed))
        assertTrue(signable(page("draft")))
        assertFalse(signable(page("active")))
    }

    @Test
    fun `the consent section stays through acceptance, signed or not`() {
        // Once saved, the section shows „Semnat” with the date instead of the pad (G7)
        for (state in listOf("draft", "submitted", "accepted")) {
            assertTrue(state, showsConsent(page(state)))
            assertTrue(state, showsConsent(page(state, signedAt = "2026-11-04T09:00:00Z")))
        }
        for (state in listOf(
            "active",
            "wrong_number",
            "unreachable",
            "refused",
            "withdrawn",
            "x"
        )) {
            assertFalse(state, showsConsent(page(state)))
        }
    }

    @Test
    fun `a card's sentence does not repeat its chip`() {
        assertEquals(null, says("wrong_number"))
        assertEquals(null, says("unreachable"))
        assertEquals(R.string.says_welcome_pending, says("accepted"))
        assertEquals(null, says("active"))
    }

    @Test
    fun `stages for an active senior`() {
        val stages = stagesOf(
            page(
                "active",
                createdAt = "c",
                submittedAt = "s",
                acceptedAt = "a",
                consentGivenAt = "g",
                consent = ConsentState("given", "call", "g")
            )
        )
        assertEquals(
            listOf(
                R.string.stage_draft,
                R.string.stage_submitted,
                R.string.stage_accepted,
                R.string.stage_active
            ),
            stages.map { it.label }
        )
        assertEquals(listOf("c", "s", "a", "g"), stages.map { it.at })
        assertTrue(stages.all { it.reached })
    }

    @Test
    fun `stages for a withdrawal keep the active date`() {
        val stages = stagesOf(
            page(
                "withdrawn",
                createdAt = "c",
                submittedAt = "s",
                acceptedAt = "a",
                consentGivenAt = "g",
                consent = ConsentState("withdrawn", "call", "w")
            )
        )
        assertEquals(5, stages.size)
        assertEquals("g", stages[3].at)
        assertEquals(R.string.stage_withdrawn, stages[4].label)
        assertEquals("w", stages[4].at)
        assertTrue(stages.all { it.reached })
    }

    @Test
    fun `a refusal reaches three stages then Refuzat`() {
        val stages = stagesOf(page("refused", consent = ConsentState("refused", "call", "r")))
        assertEquals(listOf(true, true, true, false, true), stages.map { it.reached })
        assertEquals(R.string.stage_refused, stages[4].label)
        assertEquals("r", stages[4].at)
    }

    @Test
    fun `stages from an older API have no dates`() {
        val stages = stagesOf(page("accepted"))
        assertEquals(listOf(true, true, true, false), stages.map { it.reached })
        assertTrue(stages.all { it.at == null })
        assertEquals(listOf(true, false, false, false), stagesOf(page("draft")).map { it.reached })
        assertEquals(4, stagesOf(page("paused")).size)
        assertEquals(
            listOf(true, true, false, false),
            stagesOf(page("submitted")).map {
                it.reached
            }
        )
    }

    @Test
    fun `a failed call adds its end stage`() {
        val wrong = stagesOf(page("wrong_number"))
        assertEquals(R.string.stage_wrong_number, wrong[4].label)
        assertEquals(null, wrong[4].at)
        assertTrue(wrong[4].reached)
        assertEquals(R.string.stage_unreachable, stagesOf(page("unreachable"))[4].label)
    }

    @Test
    fun `a stage date is day and month in Romanian`() {
        val date = shortDate("2026-11-04T09:30:00Z", ZoneOffset.UTC)
        assertTrue(date, date.startsWith("4 nov"))
        assertTrue(shortDate("2026-11-04T09:30:00Z", ZoneOffset.UTC, year = true).endsWith("2026"))
    }

    @Test
    fun `an unreadable date shows as sent`() {
        assertEquals("ieri", shortDate("ieri", ZoneOffset.UTC))
    }

    @Test
    fun `a consent decision or method this build does not know has no label`() {
        assertEquals(R.string.consent_withdrawn, CONSENT_DECISIONS["withdrawn"])
        assertEquals(R.string.consent_das, CONSENT_METHODS["das"])
        assertEquals(null, CONSENT_METHODS["signature"])
    }
}
