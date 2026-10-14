package bia.sentinela.enroll

import androidx.annotation.StringRes
import bia.sentinela.CaregiverForm
import bia.sentinela.R
import bia.sentinela.SeniorForm
import bia.sentinela.SeniorPage
import bia.sentinela.auth.toE164
import bia.sentinela.ui.formatPhone

// „Pacient nou” (seniors §9): the four steps, their fields, and what each step's „Continuă” sends.
// Pure, tested on the JVM.

/**
 * A field of the form. [key] is its name in the body, which is also the name FastAPI's 422 gives
 * in `loc`; [max] is the server's limit after trimming (seniors §3.5).
 */
enum class Field(
    val key: String,
    val max: Int?,
    @StringRes val label: Int,
    val phone: Boolean = false
) {
    FullName("full_name", 200, R.string.field_full_name),
    FormOfAddress("form_of_address", 120, R.string.field_form_of_address),
    Phone("phone", null, R.string.phone_label, phone = true),
    CallWindow("call_window", 60, R.string.field_call_window),
    Street("street", 200, R.string.field_street),
    StreetNumber("street_number", 20, R.string.field_street_number),
    Block("block", 20, R.string.field_block),
    Staircase("staircase", 20, R.string.field_staircase),
    Floor("floor", 20, R.string.field_floor),
    Apartment("apartment", 20, R.string.field_apartment),
    Intercom("intercom_code", 40, R.string.field_intercom),
    KeyHolder("key_holder", 200, R.string.field_key_holder),
    Landmark("landmark", 200, R.string.field_landmark),

    // The caregiver body: a mobile, because a caregiver signs in by SMS
    CaregiverName("display_name", 120, R.string.field_caregiver_name),
    Relation("relation", 60, R.string.field_relation),
    CaregiverPhone("phone", null, R.string.phone_label, phone = true)
}

/** The four steps (SE19), with the fields each one shows. */
enum class Step(@StringRes val title: Int, val fields: List<Field>) {
    Senior(
        R.string.step_senior,
        listOf(Field.FullName, Field.FormOfAddress, Field.Phone, Field.CallWindow)
    ),
    Address(
        R.string.step_address,
        listOf(
            Field.Street,
            Field.StreetNumber,
            Field.Block,
            Field.Staircase,
            Field.Floor,
            Field.Apartment,
            Field.Intercom,
            Field.KeyHolder,
            Field.Landmark
        )
    ),
    Caregivers(
        R.string.step_caregivers,
        listOf(Field.CaregiverName, Field.Relation, Field.CaregiverPhone)
    ),
    Review(R.string.step_review, emptyList());

    val next get() = entries[ordinal + 1]
    val previous get() = entries[ordinal - 1]
}

/** Steps 1 and 2 together: PUT sends the whole registration (seniors §9.2). */
val REGISTRATION = Step.Senior.fields + Step.Address.fields

enum class Problem { Required, TooLong, NotAPhone }

/** The street and its number may stay empty while the senior is a draft (SE4, 04 §2). */
fun required(field: Field, draft: Boolean): Boolean = when (field) {
    Field.FullName, Field.FormOfAddress, Field.Phone -> true
    Field.CaregiverName, Field.Relation, Field.CaregiverPhone -> true
    Field.Street, Field.StreetNumber -> !draft
    else -> false
}

/** A `+` and 8 to 15 digits once written as E.164. The server decides whether it is real. */
fun isPhone(raw: String): Boolean = Regex("^\\+\\d{8,15}$").matches(toE164(raw.trim()))

/** What is wrong with each of [fields] in [values], mirroring seniors §3.5. */
fun problems(values: Map<Field, String>, fields: List<Field>, draft: Boolean): Map<Field, Problem> =
    fields.mapNotNull { field ->
        val text = values[field].orEmpty().trim()
        val problem = when {
            text.isEmpty() -> Problem.Required.takeIf { required(field, draft) }
            field.phone && !isPhone(text) -> Problem.NotAPhone
            field.max != null && text.length > field.max -> Problem.TooLong
            else -> null
        }
        problem?.let { field to it }
    }.toMap()

/** Whether „Continuă” is enabled. Step 4 has „Trimite la DAS” or „Gata” instead. */
fun canContinue(step: Step, values: Map<Field, String>, draft: Boolean): Boolean = when (step) {
    Step.Senior, Step.Address -> problems(values, step.fields, draft).isEmpty()
    Step.Caregivers -> true
    Step.Review -> false
}

private fun Map<Field, String>.text(field: Field) = get(field).orEmpty().trim()

private fun Map<Field, String>.optional(field: Field) = text(field).ifEmpty { null }

/** The registration as POST and PUT take it: trimmed, empty as null, the number as E.164. */
fun bodyOf(values: Map<Field, String>) = SeniorForm(
    fullName = values.text(Field.FullName),
    formOfAddress = values.text(Field.FormOfAddress),
    phone = toE164(values.text(Field.Phone)),
    callWindow = values.optional(Field.CallWindow),
    street = values.optional(Field.Street),
    streetNumber = values.optional(Field.StreetNumber),
    block = values.optional(Field.Block),
    staircase = values.optional(Field.Staircase),
    floor = values.optional(Field.Floor),
    apartment = values.optional(Field.Apartment),
    intercomCode = values.optional(Field.Intercom),
    keyHolder = values.optional(Field.KeyHolder),
    landmark = values.optional(Field.Landmark)
)

fun caregiverOf(values: Map<Field, String>) = CaregiverForm(
    displayName = values.text(Field.CaregiverName),
    relation = values.text(Field.Relation),
    phone = toE164(values.text(Field.CaregiverPhone))
)

/** A saved senior in the form's fields, the number as people read it. */
fun valuesOf(page: SeniorPage): Map<Field, String> = mapOf(
    Field.FullName to page.fullName,
    Field.FormOfAddress to page.formOfAddress,
    Field.Phone to formatPhone(page.phone),
    Field.CallWindow to page.callWindow.orEmpty(),
    Field.Street to page.street.orEmpty(),
    Field.StreetNumber to page.streetNumber.orEmpty(),
    Field.Block to page.block.orEmpty(),
    Field.Staircase to page.staircase.orEmpty(),
    Field.Floor to page.floor.orEmpty(),
    Field.Apartment to page.apartment.orEmpty(),
    Field.Intercom to page.intercomCode.orEmpty(),
    Field.KeyHolder to page.keyHolder.orEmpty(),
    Field.Landmark to page.landmark.orEmpty()
)

/** What a step's „Continuă” sends (seniors §9.2). */
sealed interface Save {
    data class Create(val body: SeniorForm) : Save

    data class Update(val id: String, val body: SeniorForm) : Save

    data object None : Save
}

/**
 * Steps 1 and 2 save: POST the first time, then PUT, so a second tap never makes a second draft
 * (SE14). Step 3's buttons call the API at once, so its „Continuă” sends nothing.
 */
fun saveFor(step: Step, id: String?, values: Map<Field, String>): Save = when (step) {
    Step.Senior, Step.Address -> if (id == null) {
        Save.Create(bodyOf(values))
    } else {
        Save.Update(id, bodyOf(values))
    }

    Step.Caregivers, Step.Review -> Save.None
}

/** What submitting still needs, named as the server names it in `missing` (04 §2). */
fun missingOf(page: SeniorPage): List<String> = listOfNotNull(
    "street".takeIf { page.street.isNullOrBlank() },
    "street_number".takeIf { page.streetNumber.isNullOrBlank() },
    "caregiver".takeIf { page.caregivers.isEmpty() }
)

/** The label of each name in `missing`. A name a later server adds shows as it is. */
val MISSING_LABELS = mapOf(
    "street" to R.string.field_street,
    "street_number" to R.string.field_street_number,
    "caregiver" to R.string.missing_caregiver
)
