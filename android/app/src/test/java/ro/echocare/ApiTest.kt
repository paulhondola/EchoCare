package ro.echocare

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

// The app reads a newer server leniently (app/AGENTS.md, ADR-001 §2.3).
class ApiTest {
    // The same settings as NetworkModule.
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun aRowOfSeniorsIsDecoded() {
        val rows = json.decodeFromString<List<SeniorRow>>(
            """
            [{"id": "0199b6f0-7c1e-7a55-b8d2-5d0c8c3a7f21", "full_name": "Maria Popescu",
              "form_of_address": "doamna Maria", "phone_e164": "+40256123456",
              "phone_is_landline": true, "enrollment_state": "draft"}]
            """
        )
        assertEquals(
            listOf(
                SeniorRow(
                    id = "0199b6f0-7c1e-7a55-b8d2-5d0c8c3a7f21",
                    fullName = "Maria Popescu",
                    formOfAddress = "doamna Maria",
                    phone = "+40256123456",
                    landline = true,
                    state = "draft"
                )
            ),
            rows
        )
    }

    @Test
    fun aRowWithACodeIsDecoded() {
        val rows = json.decodeFromString<List<SeniorRow>>(
            """
            [{"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
              "phone_e164": "+40256123456", "phone_is_landline": true,
              "enrollment_state": "active", "code": "yellow",
              "reason": "Nu are căldură în casă", "since": "2026-10-17T10:00:00Z"}]
            """
        )
        assertEquals("yellow", rows.single().code)
        assertEquals("Nu are căldură în casă", rows.single().reason)
        assertEquals("2026-10-17T10:00:00Z", rows.single().since)
    }

    private val page = """
        {"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
         "phone_e164": "+40256123456", "phone_is_landline": true, "enrollment_state": "submitted",
         "street": "Str. Daliei", "street_number": "12", "block": null, "staircase": null,
         "floor": "2", "apartment": "9", "intercom_code": "09", "key_holder": null,
         "landmark": null, "call_window": "9-12",
         "medic": {"display_name": "Dr. Ion Pop", "practice": null},
         "caregivers": [{"user_id": "u1", "display_name": "Ioana Pop", "relation": "fiică",
                         "phone_e164": "+40700000004"}]}
    """

    @Test
    fun aPageIsDecodedWithItsNulls() {
        val senior = json.decodeFromString<SeniorPage>(page)
        assertEquals("Str. Daliei" to "12", senior.street to senior.streetNumber)
        assertNull(senior.block)
        assertEquals(Medic("Dr. Ion Pop", practice = null), senior.medic)
        assertEquals(
            listOf(Caregiver("u1", "Ioana Pop", "fiică", "+40700000004")),
            senior.caregivers
        )
    }

    @Test
    fun fieldsAndStatesALaterServerAddsAreNoProblem() {
        val later = page
            .replace("\"submitted\"", "\"paused\"")
            .replace("\"call_window\"", "\"code\": \"green\", \"call_window\"")
        val senior = json.decodeFromString<SeniorPage>(later)
        assertEquals("paused", senior.state)
        assertEquals("9-12", senior.callWindow)
    }

    @Test
    fun aGrantKeepsOnlyItsRole() {
        val me = json.decodeFromString<Me>(
            """{"display_name": "Ana Pop", "phone_e164": "+40700000003", "grants": [
                {"role": "caregiver", "senior_id": "s1", "senior_form_of_address": "doamna Maria",
                 "relation": "fiică"}]}"""
        )
        assertEquals(Me("Ana Pop", listOf(Grant("caregiver"))), me)
    }

    @Test
    fun anOldProfileHasNoWarning() {
        val me = json.decodeFromString<Me>("""{"display_name": "X", "grants": []}""")
        assertFalse(me.warningActive)
    }

    // GET /incidents/{id} as the local API serves it (04 §1), with a field a later server adds.
    @Test
    fun anIncidentPageIsDecoded() {
        val incident = json.decodeFromString<IncidentPage>(
            """
            {"id":"92a0","status":"open","reason":"Durere în piept, greutate la respirație",
             "opened_at":"2026-10-22T19:06:55.123456+00:00","taken_by_name":null,"taken_at":null,
             "resolved_by_name":null,"resolved_at":null,"outcome":null,"note":null,
             "handover_answered":false,"future_field":1,
             "senior":{"id":"s1","full_name":"Dumitru Pop","form_of_address":"domnul Dumitru",
               "phone_e164":"+40700000113","phone_is_landline":false,"street":"Strada Bucovinei",
               "street_number":"27","block":"H4","staircase":"A","floor":"5","apartment":"31",
               "intercom_code":"31","key_holder":"Fiica, Simona, are cheie de rezervă",
               "landmark":"Lângă parcul din cartier"},
             "caregivers":[{"display_name":"Simona Pop","phone_e164":"+40700000211","relation":"fiică"}],
             "event":{"type":"sos_button","measured_at":"2026-10-22T19:05:00+00:00",
               "latitude":45.7489,"longitude":21.2087,"location_accuracy_m":14,"located_at":null},
             "calls":[{"id":"c1","trigger":"watch","attempt":1,"state":"handed_over",
               "started_at":"2026-10-22T19:06:30+00:00","ended_at":null,"final_severity":"red",
               "final_certainty":null,"reason":null,"summary":null,"handover_answered":null,
               "reports":[{"source":"agent","severity":"red","certainty":null,
                 "reason":"Durere în piept, greutate la respirație",
                 "quote":"Mă strânge în piept și nu pot respira bine.",
                 "at":"2026-10-22T19:06:42+00:00"}],
               "turns":[{"speaker":"senior","kind":"speech",
                 "content":"Mă strânge în piept și nu pot respira bine.",
                 "at":"2026-10-22T19:06:41+00:00"}]}]}
            """
        )
        assertEquals("Strada Bucovinei", incident.senior.street)
        assertEquals(14.0, incident.event?.accuracy)
        assertNull(incident.calls.single().handoverAnswered)
        assertEquals(
            "Mă strânge în piept și nu pot respira bine.",
            incident.calls.single().reports.single().quote
        )
        assertEquals("fiică", incident.caregivers.single().relation)
    }
}
