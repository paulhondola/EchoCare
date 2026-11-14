import Foundation

// „Pacient nou” (seniors §9): the four steps, their fields, and what each step's „Continuă” sends.
// Pure, ported from android/app/.../enroll/Form.kt; FormTests.swift ports FormTest.kt.

/// A field of the form. `key` is its name in the body, which is also the name FastAPI's 422 gives
/// in `loc`; `max` is the server's limit after trimming (seniors §3.5). `label` is a
/// `Localizable.xcstrings` key.
enum Field: CaseIterable, Hashable, Sendable {
    case fullName, formOfAddress, phone, callWindow
    case street, streetNumber, block, staircase, floor, apartment, intercom, keyHolder, landmark
    // The caregiver body: a mobile, because a caregiver signs in by SMS
    case caregiverName, relation, caregiverPhone

    var key: String {
        switch self {
        case .fullName: "full_name"
        case .formOfAddress: "form_of_address"
        case .phone, .caregiverPhone: "phone"
        case .callWindow: "call_window"
        case .street: "street"
        case .streetNumber: "street_number"
        case .block: "block"
        case .staircase: "staircase"
        case .floor: "floor"
        case .apartment: "apartment"
        case .intercom: "intercom_code"
        case .keyHolder: "key_holder"
        case .landmark: "landmark"
        case .caregiverName: "display_name"
        case .relation: "relation"
        }
    }

    var max: Int? {
        switch self {
        case .fullName: 200
        case .formOfAddress: 120
        case .phone, .caregiverPhone: nil
        case .callWindow: 60
        case .street: 200
        case .streetNumber, .block, .staircase, .floor, .apartment: 20
        case .intercom: 40
        case .keyHolder, .landmark: 200
        case .caregiverName: 120
        case .relation: 60
        }
    }

    var label: String {
        switch self {
        case .fullName: "field_full_name"
        case .formOfAddress: "field_form_of_address"
        case .phone, .caregiverPhone: "phone_label"
        case .callWindow: "field_call_window"
        case .street: "field_street"
        case .streetNumber: "field_street_number"
        case .block: "field_block"
        case .staircase: "field_staircase"
        case .floor: "field_floor"
        case .apartment: "field_apartment"
        case .intercom: "field_intercom"
        case .keyHolder: "field_key_holder"
        case .landmark: "field_landmark"
        case .caregiverName: "field_caregiver_name"
        case .relation: "field_relation"
        }
    }

    var isPhone: Bool { self == .phone || self == .caregiverPhone }
}

/// The four steps (SE19), with the fields each one shows. `title` is a `Localizable.xcstrings` key.
enum Step: Int, CaseIterable, Hashable, Sendable {
    case senior, address, caregivers, review

    var title: String {
        switch self {
        case .senior: "step_senior"
        case .address: "step_address"
        case .caregivers: "step_caregivers"
        case .review: "step_review"
        }
    }

    var fields: [Field] {
        switch self {
        case .senior: [.fullName, .formOfAddress, .phone, .callWindow]
        case .address:
            [
                .street, .streetNumber, .block, .staircase, .floor, .apartment, .intercom,
                .keyHolder, .landmark,
            ]
        case .caregivers: [.caregiverName, .relation, .caregiverPhone]
        case .review: []
        }
    }

    var next: Step { Step(rawValue: rawValue + 1)! }
    var previous: Step { Step(rawValue: rawValue - 1)! }
}

/// Steps 1 and 2 together: PUT sends the whole registration (seniors §9.2).
let REGISTRATION = Step.senior.fields + Step.address.fields

enum Problem: Equatable, Sendable { case required, tooLong, notAPhone }

/// The street and its number may stay empty while the senior is a draft (SE4, 04 §2).
func required(_ field: Field, draft: Bool) -> Bool {
    switch field {
    case .fullName, .formOfAddress, .phone, .caregiverName, .relation, .caregiverPhone: true
    case .street, .streetNumber: !draft
    default: false
    }
}

/// A `+` and 8 to 15 digits once written as E.164. The server decides whether it is real.
func isPhone(_ raw: String) -> Bool {
    // ASCII digits, as Kotlin's `\d`: Swift's matches every script's
    toE164(raw.trimmed).wholeMatch(of: /\+[0-9]{8,15}/) != nil
}

extension String {
    /// Without the whitespace and line breaks at either end, as Kotlin's `trim()`.
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}

/// What is wrong with each of `fields` in `values`, mirroring seniors §3.5.
func problems(_ values: [Field: String], _ fields: [Field], draft: Bool) -> [Field: Problem] {
    var found: [Field: Problem] = [:]
    for field in fields {
        let text = (values[field] ?? "").trimmed
        if text.isEmpty {
            if required(field, draft: draft) { found[field] = .required }
        } else if field.isPhone && !isPhone(text) {
            found[field] = .notAPhone
            // The server counts characters, not UTF-16 units: a scalar is the nearest here
        } else if let max = field.max, text.unicodeScalars.count > max {
            found[field] = .tooLong
        }
    }
    return found
}

/// Whether „Continuă” is enabled. Step 4 has „Trimite la DAS” or „Gata” instead.
func canContinue(_ step: Step, _ values: [Field: String], draft: Bool) -> Bool {
    switch step {
    case .senior, .address: problems(values, step.fields, draft: draft).isEmpty
    case .caregivers: true
    case .review: false
    }
}

private func text(_ values: [Field: String], _ field: Field) -> String {
    (values[field] ?? "").trimmed
}

private func optional(_ values: [Field: String], _ field: Field) -> String? {
    let value = text(values, field)
    return value.isEmpty ? nil : value
}

/// „Echipamente” (UC-01, design 2026-11-14), in the order the server stores them.
let EQUIPMENT = ["smartphone", "watch", "home_node"]

/// What to send for the ticked boxes: a watch or a home node talks only to the phone's app.
func equipmentOf(_ ticked: Set<String>) -> [String] {
    let needsApp = ticked.contains("watch") || ticked.contains("home_node")
    return EQUIPMENT.filter { ticked.contains($0) || ($0 == "smartphone" && needsApp) }
}

/// The saved boxes; nil while the equipment is not stated, which the form leaves as it is.
func equipmentIn(_ page: SeniorPage) -> Set<String>? { page.equipment.map(Set.init) }

/// Whether the number can have the phone app: it signs in by SMS. shortcut: Romanian numbers only,
/// as the form takes; the server's 422 has the last word.
func isMobile(_ raw: String) -> Bool { toE164(raw.trimmed).hasPrefix("+407") }

/// The registration as POST and PUT take it: trimmed, empty as null, the number as E.164.
func bodyOf(_ values: [Field: String], equipment: Set<String>? = nil) -> SeniorForm {
    // A landline has no app, so none of the devices that talk to it (UC-01)
    let kit = equipment.map { isMobile(text(values, .phone)) ? equipmentOf($0) : [] }
    return SeniorForm(
        fullName: text(values, .fullName),
        formOfAddress: text(values, .formOfAddress),
        phone: toE164(text(values, .phone)),
        callWindow: optional(values, .callWindow),
        street: optional(values, .street),
        streetNumber: optional(values, .streetNumber),
        block: optional(values, .block),
        staircase: optional(values, .staircase),
        floor: optional(values, .floor),
        apartment: optional(values, .apartment),
        intercomCode: optional(values, .intercom),
        keyHolder: optional(values, .keyHolder),
        landmark: optional(values, .landmark),
        equipment: kit)
}

func caregiverOf(_ values: [Field: String]) -> CaregiverForm {
    CaregiverForm(
        displayName: text(values, .caregiverName),
        relation: text(values, .relation),
        phone: toE164(text(values, .caregiverPhone)))
}

/// A saved senior in the form's fields, the number as people read it.
func valuesOf(_ page: SeniorPage) -> [Field: String] {
    [
        .fullName: page.fullName,
        .formOfAddress: page.formOfAddress,
        .phone: formatPhone(page.phone),
        .callWindow: page.callWindow ?? "",
        .street: page.street ?? "",
        .streetNumber: page.streetNumber ?? "",
        .block: page.block ?? "",
        .staircase: page.staircase ?? "",
        .floor: page.floor ?? "",
        .apartment: page.apartment ?? "",
        .intercom: page.intercomCode ?? "",
        .keyHolder: page.keyHolder ?? "",
        .landmark: page.landmark ?? "",
    ]
}

/// What a step's „Continuă” sends (seniors §9.2).
enum Save: Equatable, Sendable {
    case create(SeniorForm)
    case update(id: String, SeniorForm)
    case none
}

/// Steps 1 and 2 save: POST the first time, then PUT, so a second tap never makes a second draft
/// (SE14). Step 3's buttons call the API at once, so its „Continuă” sends nothing.
func saveFor(
    _ step: Step, id: String?, _ values: [Field: String], equipment: Set<String>? = nil
) -> Save {
    switch step {
    case .senior, .address:
        let body = bodyOf(values, equipment: equipment)
        return if let id { .update(id: id, body) } else { .create(body) }
    case .caregivers, .review: return .none
    }
}

/// What submitting still needs, named as the server names it in `missing` (04 §2).
func missingOf(_ page: SeniorPage) -> [String] {
    var missing: [String] = []
    if (page.street ?? "").trimmed.isEmpty { missing.append("street") }
    if (page.streetNumber ?? "").trimmed.isEmpty { missing.append("street_number") }
    if page.caregivers.isEmpty { missing.append("caregiver") }
    return missing
}

/// The label (a `Localizable.xcstrings` key) of each name in `missing`. A name a later server adds
/// shows as it is.
let MISSING_LABELS = [
    "street": "field_street", "street_number": "field_street_number",
    "caregiver": "missing_caregiver",
]
