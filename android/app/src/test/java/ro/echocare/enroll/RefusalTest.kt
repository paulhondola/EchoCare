package ro.echocare.enroll

import java.io.IOException
import kotlinx.coroutines.runBlocking
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import ro.echocare.R
import ro.echocare.home.Failure

// seniors §9.3: one reader for both refusal bodies, and what the form does with each.
class RefusalTest {
    // FastAPI's own 422, as the backend sends it for a number that does not parse.
    private val badPhone = """
        {"detail": [{"type": "value_error", "loc": ["body", "phone"],
                     "msg": "Value error, not a valid phone number", "input": "0700",
                     "ctx": {"error": {}}}]}
    """

    @Test
    fun fastApisListNamesTheFields() {
        assertEquals(Refusal.Invalid(listOf("phone")), refusalOf(422, badPhone))
        assertEquals(
            Refusal.Invalid(listOf("display_name", "relation")),
            refusalOf(
                422,
                """{"detail": [{"loc": ["body", "display_name"]}, {"loc": ["body", "relation"]},
                               {"loc": ["body", "relation"]}]}"""
            )
        )
        // The body as a whole, or a path parameter: no field of the form to mark.
        assertEquals(
            Refusal.Invalid(emptyList()),
            refusalOf(422, """{"detail": [{"loc": ["body"]}, {"loc": ["path", "senior_id"]}]}""")
        )
        assertEquals(Refusal.Invalid(emptyList()), refusalOf(422, "not json"))
    }

    @Test
    fun ourBodyGivesTheReason() {
        assertEquals(
            Refusal.Incomplete(listOf("street", "street_number", "caregiver")),
            refusalOf(
                422,
                """{"detail": {"reason": "incomplete",
                               "missing": ["street", "street_number", "caregiver"]}}"""
            )
        )
        assertEquals(
            Refusal.Incomplete(emptyList()),
            refusalOf(422, """{"detail": {"reason": "incomplete"}}""")
        )
        assertEquals(
            Refusal.AlreadyDone,
            refusalOf(409, """{"detail": {"reason": "already_done"}}""")
        )
        assertEquals(
            Refusal.WrongState,
            refusalOf(409, """{"detail": {"reason": "wrong_state"}}""")
        )
        // A reason a later server adds: the senior is read again, never a crash (ADR-001 §2.3).
        assertEquals(Refusal.WrongState, refusalOf(409, """{"detail": {"reason": "paused"}}"""))
    }

    @Test
    fun everythingElseIsAsForAReadInSlice3() {
        assertEquals(
            Refusal.Failed(Failure.NotFound),
            refusalOf(404, """{"detail": {"reason": "not_found"}}""")
        )
        assertEquals(
            Refusal.Failed(Failure.NotAllowed),
            refusalOf(403, """{"detail": {"reason": "not_allowed"}}""")
        )
        assertEquals(
            Refusal.Failed(Failure.NotRegistered),
            refusalOf(403, """{"detail": {"reason": "not_registered"}}""")
        )
        assertEquals(
            Refusal.Failed(Failure.SignedOut),
            refusalOf(401, """{"detail": {"reason": "not_signed_in"}}""")
        )
        assertEquals(Refusal.Failed(Failure.NoConnection), refusalOf(502, "<html>502</html>"))
        assertEquals(Refusal.Failed(Failure.NoConnection), refusalOf(null, null))
    }

    @Test
    fun aRefusedSaveMarksTheFieldsOrSaysWhy() {
        assertEquals(
            Then.Mark(mapOf(Field.Phone to R.string.invalid_phone)),
            thenAfter(Action.Save, Refusal.Invalid(listOf("phone")))
        )
        assertEquals(
            Then.Mark(mapOf(Field.FullName to R.string.field_invalid)),
            thenAfter(Action.Save, Refusal.Invalid(listOf("full_name", "unknown")))
        )
        assertEquals(
            Then.Show(Notice.Says(R.string.field_invalid)),
            thenAfter(Action.Save, Refusal.Invalid(emptyList()))
        )
        // A submitted senior keeps the street and number (04 §2).
        assertEquals(
            Then.Show(Notice.Missing(listOf("street"))),
            thenAfter(Action.Save, Refusal.Incomplete(listOf("street")))
        )
        assertEquals(Then.Reread, thenAfter(Action.Save, Refusal.WrongState))
    }

    @Test
    fun phoneTakenMarksThePhone() {
        val body = """{"detail": {"reason": "phone_taken"}}"""
        assertEquals(Refusal.PhoneTaken, refusalOf(409, body))
        assertEquals(
            Then.Mark(mapOf(Field.Phone to R.string.phone_taken)),
            thenAfter(Action.Save, Refusal.PhoneTaken)
        )
    }

    @Test
    fun aRefusedCaregiverSaysWhy() {
        assertEquals(
            Then.Mark(mapOf(Field.CaregiverPhone to R.string.caregiver_phone_invalid)),
            thenAfter(Action.Add, Refusal.Invalid(listOf("phone")))
        )
        assertEquals(
            Then.Mark(
                mapOf(
                    Field.CaregiverName to R.string.field_invalid,
                    Field.Relation to R.string.field_invalid
                )
            ),
            thenAfter(Action.Add, Refusal.Invalid(listOf("display_name", "relation")))
        )
        assertEquals(
            Then.Show(Notice.Says(R.string.already_caregiver)),
            thenAfter(Action.Add, Refusal.AlreadyDone)
        )
        // Past draft the last caregiver stays (04 §2).
        assertEquals(
            Then.Show(Notice.Says(R.string.last_caregiver)),
            thenAfter(Action.Remove, Refusal.Incomplete(listOf("caregiver")))
        )
    }

    @Test
    fun aRefusedSubmitNamesWhatIsMissingOrRereads() {
        assertEquals(
            Then.Show(Notice.Missing(listOf("street_number", "caregiver"))),
            thenAfter(Action.Submit, Refusal.Incomplete(listOf("street_number", "caregiver")))
        )
        // Already submitted, or past it: step 4 shows the state the senior is in.
        assertEquals(Then.Reread, thenAfter(Action.Submit, Refusal.WrongState))
        assertEquals(Then.Reread, thenAfter(Action.Submit, Refusal.AlreadyDone))
    }

    @Test
    fun noConnectionKeepsTheFormAndTheRestStopIt() {
        for (action in Action.entries) {
            assertEquals(
                Then.Show(Notice.Says(R.string.no_connection)),
                thenAfter(action, Refusal.Failed(Failure.NoConnection))
            )
            for (failure in Failure.entries - Failure.NoConnection) {
                assertEquals(Then.Stop(failure), thenAfter(action, Refusal.Failed(failure)))
            }
        }
    }

    @Test
    fun aCommandBecomesWhatItsAnswerMeans() = runBlocking {
        assertEquals(Sent.Ok("s1"), send { "s1" })
        assertEquals(
            Sent.No(Refusal.Invalid(listOf("phone"))),
            send { throw HttpException(Response.error<Unit>(422, badPhone.toResponseBody())) }
        )
        assertEquals(
            Sent.No(Refusal.Failed(Failure.NoConnection)),
            send { throw IOException("timeout") }
        )
    }

    @Test
    fun aRemovalChecksItsStatus() = runBlocking {
        assertEquals(Unit, ensure(Response.success(204, Unit)))
        val refused = send {
            ensure(
                Response.error<Unit>(
                    422,
                    """{"detail": {"reason": "incomplete", "missing": ["caregiver"]}}"""
                        .toResponseBody()
                )
            )
        }
        assertEquals(Sent.No(Refusal.Incomplete(listOf("caregiver"))), refused)
    }
}
