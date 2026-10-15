package bia.sentinela.enroll

import bia.sentinela.Caregiver
import bia.sentinela.CaregiverForm
import bia.sentinela.Medic
import bia.sentinela.R
import bia.sentinela.SeniorForm
import bia.sentinela.SeniorPage
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

// seniors §9.2 and §9.3: validation, and what each step's „Continuă” sends.
class FormTest {
    private val step1 = mapOf(
        Field.FullName to "Maria Popescu",
        Field.FormOfAddress to "doamna Maria",
        Field.Phone to "0256 123 456"
    )
    private val all = step1 + mapOf(
        Field.CallWindow to "9-12",
        Field.Street to "Str. Daliei",
        Field.StreetNumber to "12",
        Field.Block to "B3",
        Field.Staircase to "A",
        Field.Floor to "2",
        Field.Apartment to "9",
        Field.Intercom to "09",
        Field.KeyHolder to "vecina de la ap. 10",
        Field.Landmark to "lângă farmacie"
    )
    private val body = SeniorForm(
        fullName = "Maria Popescu",
        formOfAddress = "doamna Maria",
        phone = "+40256123456",
        callWindow = "9-12",
        street = "Str. Daliei",
        streetNumber = "12",
        block = "B3",
        staircase = "A",
        floor = "2",
        apartment = "9",
        intercomCode = "09",
        keyHolder = "vecina de la ap. 10",
        landmark = "lângă farmacie"
    )

    @Test
    fun step1NeedsANameAFormOfAddressAndANumber() {
        assertEquals(
            mapOf(
                Field.FullName to Problem.Required,
                Field.FormOfAddress to Problem.Required,
                Field.Phone to Problem.Required
            ),
            problems(emptyMap(), Step.Senior.fields, draft = true)
        )
        assertTrue(problems(step1, Step.Senior.fields, draft = true).isEmpty())
    }

    @Test
    fun blankIsEmpty() {
        val blank = step1 + (Field.FullName to "   ")
        assertEquals(
            mapOf(Field.FullName to Problem.Required),
            problems(blank, Step.Senior.fields, draft = true)
        )
    }

    @Test
    fun limitsCountAfterTrimming() {
        fun problem(field: Field, text: String) =
            problems(mapOf(field to text), listOf(field), draft = true)[field]
        assertEquals(null, problem(Field.FullName, " " + "a".repeat(200) + " "))
        assertEquals(Problem.TooLong, problem(Field.FullName, "a".repeat(201)))
        assertEquals(Problem.TooLong, problem(Field.FormOfAddress, "a".repeat(121)))
        assertEquals(Problem.TooLong, problem(Field.CallWindow, "a".repeat(61)))
        assertEquals(null, problem(Field.StreetNumber, "a".repeat(20)))
        assertEquals(Problem.TooLong, problem(Field.StreetNumber, "a".repeat(21)))
        assertEquals(Problem.TooLong, problem(Field.Intercom, "a".repeat(41)))
        assertEquals(Problem.TooLong, problem(Field.Landmark, "a".repeat(201)))
        assertEquals(Problem.TooLong, problem(Field.CaregiverName, "a".repeat(121)))
        assertEquals(Problem.TooLong, problem(Field.Relation, "a".repeat(61)))
    }

    @Test
    fun aNumberIsAPlusAndEightToFifteenDigits() {
        for (ok in listOf(
            "0722 123 456",
            "0722-123-456",
            "+40 256 123 456",
            "0040722123456",
            "722123456",
            "+4930123456"
        )) {
            assertTrue(ok, isPhone(ok))
        }
        for (bad in listOf("", "07", "0722 12", "abc", "+4072212345678901", "0722 abc 456")) {
            assertFalse(bad, isPhone(bad))
        }
        assertEquals(
            Problem.NotAPhone,
            problems(step1 + (Field.Phone to "07"), Step.Senior.fields, draft = true)[Field.Phone]
        )
    }

    @Test
    fun aDraftMayLeaveTheStreetAndNumberEmptyButNotLater() {
        assertTrue(problems(step1, Step.Address.fields, draft = true).isEmpty())
        assertEquals(
            mapOf(Field.Street to Problem.Required, Field.StreetNumber to Problem.Required),
            problems(step1, Step.Address.fields, draft = false)
        )
        assertTrue(problems(all, Step.Address.fields, draft = false).isEmpty())
    }

    @Test
    fun continueIsEnabledWhenTheStepIsValid() {
        assertFalse(canContinue(Step.Senior, emptyMap(), draft = true))
        assertFalse(canContinue(Step.Senior, step1 - Field.Phone, draft = true))
        assertTrue(canContinue(Step.Senior, step1, draft = true))
        assertTrue(canContinue(Step.Address, step1, draft = true))
        assertFalse(canContinue(Step.Address, step1, draft = false))
        // Step 3 sends nothing; step 4 has its own button.
        assertTrue(canContinue(Step.Caregivers, emptyMap(), draft = true))
        assertFalse(canContinue(Step.Review, all, draft = true))
    }

    @Test
    fun theBodyIsTrimmedWithEmptyFieldsAsNull() {
        val typed = mapOf(
            Field.FullName to "  Maria Popescu ",
            Field.FormOfAddress to "doamna Maria",
            Field.Phone to " 0722 123 456 ",
            Field.Street to "",
            Field.Block to "   "
        )
        assertEquals(
            SeniorForm(
                fullName = "Maria Popescu",
                formOfAddress = "doamna Maria",
                phone = "+40722123456",
                callWindow = null,
                street = null,
                streetNumber = null,
                block = null,
                staircase = null,
                floor = null,
                apartment = null,
                intercomCode = null,
                keyHolder = null,
                landmark = null
            ),
            bodyOf(typed)
        )
    }

    @Test
    fun theBodyNamesEveryFieldOfTheRegistrationAndSendsItsNulls() {
        // PUT replaces every field, so a field left out would be emptied (seniors §3.5).
        val json = Json { ignoreUnknownKeys = true }.encodeToJsonElement(bodyOf(step1)).jsonObject
        assertEquals(REGISTRATION.map { it.key }.toSet(), json.keys)
        assertEquals(JsonNull, json["street"])
    }

    private val page = SeniorPage(
        id = "s1",
        fullName = "Maria Popescu",
        formOfAddress = "doamna Maria",
        phone = "+40256123456",
        landline = true,
        state = "submitted",
        street = "Str. Daliei",
        streetNumber = "12",
        block = "B3",
        staircase = "A",
        floor = "2",
        apartment = "9",
        intercomCode = "09",
        keyHolder = "vecina de la ap. 10",
        landmark = "lângă farmacie",
        callWindow = "9-12",
        medic = Medic("Dr. Ion Pop"),
        caregivers = listOf(Caregiver("u1", "Ioana Pop", "fiică", "+40700000004"))
    )

    @Test
    fun aSavedSeniorFillsTheForm() {
        val values = valuesOf(page)
        assertEquals("021 234 5678", valuesOf(page.copy(phone = "+40212345678"))[Field.Phone])
        assertEquals("0256 123 456", values[Field.Phone])
        // Saving again without a change sends what was saved.
        assertEquals(body, bodyOf(values))
        assertEquals("", valuesOf(page.copy(block = null))[Field.Block])
    }

    @Test
    fun step1CreatesTheSeniorTheFirstTimeAndSavesAfterThat() {
        assertEquals(Save.Create(bodyOf(step1)), saveFor(Step.Senior, id = null, step1))
        assertEquals(Save.Update("s1", bodyOf(step1)), saveFor(Step.Senior, id = "s1", step1))
    }

    @Test
    fun step2SendsTheWholeRegistration() {
        assertEquals(Save.Update("s1", body), saveFor(Step.Address, id = "s1", all))
    }

    @Test
    fun step3SendsNothing() {
        // „Adaugă” and „Elimină” call the API at once (seniors §9.2).
        assertEquals(Save.None, saveFor(Step.Caregivers, id = "s1", all))
        assertEquals(Save.None, saveFor(Step.Review, id = "s1", all))
    }

    @Test
    fun aCaregiverIsTrimmedWithTheNumberAsE164() {
        val typed = mapOf(
            Field.CaregiverName to " Ioana Pop ",
            Field.Relation to "fiică ",
            Field.CaregiverPhone to "0700 000 004"
        )
        assertEquals(CaregiverForm("Ioana Pop", "fiică", "+40700000004"), caregiverOf(typed))
        assertTrue(problems(typed, Step.Caregivers.fields, draft = true).isEmpty())
        assertEquals(
            setOf(Field.CaregiverName, Field.Relation, Field.CaregiverPhone),
            problems(emptyMap(), Step.Caregivers.fields, draft = true).keys
        )
    }

    @Test
    fun submittingNeedsTheStreetItsNumberAndACaregiver() {
        assertEquals(emptyList<String>(), missingOf(page))
        assertEquals(
            listOf("street", "street_number", "caregiver"),
            missingOf(page.copy(street = null, streetNumber = " ", caregivers = emptyList()))
        )
        // Every name the server sends in `missing` has a label (04 §2).
        assertEquals(
            mapOf(
                "street" to R.string.field_street,
                "street_number" to R.string.field_street_number,
                "caregiver" to R.string.missing_caregiver
            ),
            MISSING_LABELS
        )
    }

    @Test
    fun theStepsAreInOrder() {
        assertEquals(
            listOf(
                R.string.step_senior,
                R.string.step_address,
                R.string.step_caregivers,
                R.string.step_review
            ),
            Step.entries.map { it.title }
        )
        assertEquals(Step.Address, Step.Senior.next)
        assertEquals(Step.Senior, Step.Address.previous)
    }
}
