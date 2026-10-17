package ro.echocare.home

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ro.echocare.MockAnswer
import ro.echocare.MockCall

// design §6.2: the mock call card's answer is what the server's MockAnswerForm reads (§4.2).
class MockCallTest {
    // The same settings as NetworkModule: defaults (the nulls, declined = false) are not sent.
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun anAnswerNeedsAllThree() {
        assertNull(campaignAnswer("ok", null, "yes"))
        assertEquals(
            MockAnswer(feeling = "ok", day = "marți", shelter = "yes"),
            campaignAnswer("ok", "marți", "yes")
        )
    }

    @Test
    fun answersAreSentAsTheServerReadsThem() {
        assertEquals("""{"declined":true}""", json.encodeToString(MockAnswer(declined = true)))
        assertEquals("""{"consent":false}""", json.encodeToString(MockAnswer(consent = false)))
        assertEquals(
            """{"feeling":"unwell","day":"sâmbătă","shelter":"no"}""",
            json.encodeToString(campaignAnswer("unwell", "sâmbătă", "no")!!)
        )
    }

    @Test
    fun aWelcomeCallIsDecoded() {
        val call = json.decodeFromString<MockCall>(
            """{"call_id": "c1", "trigger": "welcome", "consent_text": "Sunteți de acord?", "text_version": "v1-app"}"""
        )
        assertEquals(MockCall("c1", "welcome", consentText = "Sunteți de acord?"), call)
    }

    @Test
    fun aDefiniteReadSetsTheCardAndALostOneKeepsIt() {
        val shown = MockCall("c1", "campaign")
        val next = MockCall("c2", "welcome")
        assertEquals(next, cardAfterRead(200, next, shown))
        // 204 (nothing due), 403 and 404 (production) are the server's answer: no card
        for (status in listOf(204, 403, 404)) assertNull(cardAfterRead(status, null, shown))
        // A redeploy's 502 or 503, or no connection at all (null), keeps what the senior is on
        for (status in listOf(500, 502, 503, null)) {
            assertEquals(shown, cardAfterRead(status, null, shown))
        }
    }

    @Test
    fun aPostSettlesTheCardOnlyWhenTheServerAnswered() {
        // 204, and 409 or 422: the call is done or the body was refused, so the page rereads
        for (status in listOf(204, 409, 422)) assertTrue(answerSettled(status))
        // The answer may not have arrived: the card stays so the senior can press again
        for (status in listOf(500, 502, 503, null)) assertFalse(answerSettled(status))
    }

    @Test
    fun theDaysAreTheServers() {
        assertEquals(7, DAYS.size)
        assertEquals("sâmbătă", DAYS[5])
    }
}
