package ro.echocare.home

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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
    fun theDaysAreTheServers() {
        assertEquals(7, DAYS.size)
        assertEquals("sâmbătă", DAYS[5])
    }
}
