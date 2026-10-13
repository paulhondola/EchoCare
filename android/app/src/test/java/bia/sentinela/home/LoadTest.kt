package bia.sentinela.home

import java.io.IOException
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.SerializationException
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

// seniors §8.2: what a list or a page shows for each answer.
class LoadTest {
    private val list = listOf("doamna Maria")
    private val lost = Answer.No(Failure.NoConnection)

    @Test
    fun statusesBecomeFailures() {
        assertEquals(Failure.SignedOut, failureOf(401, "not_signed_in"))
        assertEquals(Failure.NotRegistered, failureOf(403, "not_registered"))
        assertEquals(Failure.NotAllowed, failureOf(403, "not_allowed"))
        // A 403 with no readable reason is not a reason to sign the person out.
        assertEquals(Failure.NotAllowed, failureOf(403, null))
        assertEquals(Failure.NotFound, failureOf(404, "not_found"))
        assertEquals(Failure.NoConnection, failureOf(503, "auth_unavailable"))
        assertEquals(Failure.NoConnection, failureOf(500, null))
        assertEquals(Failure.NoConnection, failureOf(null, null))
    }

    @Test
    fun onlySignedOutAndNotRegisteredEndTheSession() {
        assertEquals(
            listOf(Failure.SignedOut, Failure.NotRegistered),
            Failure.entries.filter { it.endsSession }
        )
    }

    @Test
    fun reasonIsReadFromARefusalBody() {
        assertEquals("not_registered", reasonOf("""{"detail": {"reason": "not_registered"}}"""))
        assertEquals(
            "already_done",
            reasonOf("""{"detail": {"reason": "already_done", "taken_by_name": "Ana"}}""")
        )
    }

    @Test
    fun anyOtherBodyHasNoReason() {
        // FastAPI's own 422: a list under "detail".
        assertNull(reasonOf("""{"detail": [{"loc": ["body", "phone"], "msg": "bad"}]}"""))
        assertNull(reasonOf("""{"detail": "Not Found"}"""))
        assertNull(reasonOf("<html>502 Bad Gateway</html>"))
        assertNull(reasonOf(""))
        assertNull(reasonOf("{}"))
        assertNull(reasonOf(null))
    }

    @Test
    fun anAnswerReplacesWhateverWasShown() {
        assertEquals(Load.Ready(list), Load.Loading.after(Answer.Ok(list)))
        assertEquals(
            Load.Ready(list),
            Load.Ready(listOf("old"), offline = true).after(Answer.Ok(list))
        )
        assertEquals(Load.Ready(list), Load.Failed(Failure.NoConnection).after(Answer.Ok(list)))
    }

    @Test
    fun withNothingOnScreenALostConnectionIsShown() {
        assertEquals(Load.Failed(Failure.NoConnection), Load.Loading.after<List<String>>(lost))
        assertEquals(
            Load.Failed(Failure.NoConnection),
            Load.Failed(Failure.NoConnection).after<List<String>>(lost)
        )
    }

    @Test
    fun withDataOnScreenALostConnectionKeepsItUnderTheBanner() {
        val shown: Load<List<String>> = Load.Ready(list)
        assertEquals(Load.Ready(list, offline = true), shown.after(lost))
        // And it stays there on the next failed re-read.
        assertEquals(Load.Ready(list, offline = true), shown.after(lost).after(lost))
    }

    @Test
    fun aRefusalReplacesTheDataEvenWhenSomeIsShown() {
        val shown: Load<List<String>> = Load.Ready(list)
        for (failure in Failure.entries - Failure.NoConnection) {
            assertEquals(Load.Failed(failure), shown.after(Answer.No(failure)))
            assertEquals(Load.Failed(failure), Load.Loading.after<List<String>>(Answer.No(failure)))
        }
    }

    private fun refused(status: Int, body: String) =
        HttpException(Response.error<Unit>(status, body.toResponseBody()))

    @Test
    fun aCallBecomesAnAnswer() = runBlocking {
        assertEquals(Answer.Ok(list), answer { list })
        assertEquals(
            Answer.No(Failure.NotRegistered),
            answer { throw refused(403, """{"detail": {"reason": "not_registered"}}""") }
        )
        assertEquals(Answer.No(Failure.NotFound), answer { throw refused(404, "{}") })
        assertEquals(Answer.No(Failure.NoConnection), answer { throw IOException("timeout") })
        // A body this build cannot read is treated as no answer, never as a crash.
        assertEquals(
            Answer.No(Failure.NoConnection),
            answer { throw SerializationException("unexpected JSON") }
        )
    }

    @Test
    fun offlineIsOffByDefault() {
        assertFalse(Load.Ready(list).offline)
        assertTrue((Load.Ready(list).after(lost) as Load.Ready).offline)
    }
}
