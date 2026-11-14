import Foundation
import Testing

@testable import EchoCare

// seniors §9.2 and §9.3: validation, and what each step's „Continuă” sends. Ported from android's
// FormTest.kt.
struct FormTests {
    private let step1: [Field: String] = [
        .fullName: "Maria Popescu",
        .formOfAddress: "doamna Maria",
        .phone: "0256 123 456",
    ]
    private var all: [Field: String] {
        step1.merging([
            .callWindow: "9-12",
            .street: "Str. Daliei",
            .streetNumber: "12",
            .block: "B3",
            .staircase: "A",
            .floor: "2",
            .apartment: "9",
            .intercom: "09",
            .keyHolder: "vecina de la ap. 10",
            .landmark: "lângă farmacie",
        ]) { $1 }
    }
    private let body = SeniorForm(
        fullName: "Maria Popescu", formOfAddress: "doamna Maria", phone: "+40256123456",
        callWindow: "9-12", street: "Str. Daliei", streetNumber: "12", block: "B3", staircase: "A",
        floor: "2", apartment: "9", intercomCode: "09", keyHolder: "vecina de la ap. 10",
        landmark: "lângă farmacie")

    @Test func `step 1 needs a name a form of address and a number`() {
        #expect(
            problems([:], Step.senior.fields, draft: true) == [
                .fullName: .required, .formOfAddress: .required, .phone: .required,
            ])
        #expect(problems(step1, Step.senior.fields, draft: true).isEmpty)
    }

    @Test func `blank is empty`() {
        let blank = step1.merging([.fullName: "   "]) { $1 }
        #expect(problems(blank, Step.senior.fields, draft: true) == [.fullName: .required])
    }

    @Test func `limits count after trimming`() {
        func problem(_ field: Field, _ text: String) -> Problem? {
            problems([field: text], [field], draft: true)[field]
        }
        #expect(problem(.fullName, " " + String(repeating: "a", count: 200) + " ") == nil)
        #expect(problem(.fullName, String(repeating: "a", count: 201)) == .tooLong)
        #expect(problem(.formOfAddress, String(repeating: "a", count: 121)) == .tooLong)
        #expect(problem(.callWindow, String(repeating: "a", count: 61)) == .tooLong)
        #expect(problem(.streetNumber, String(repeating: "a", count: 20)) == nil)
        #expect(problem(.streetNumber, String(repeating: "a", count: 21)) == .tooLong)
        #expect(problem(.intercom, String(repeating: "a", count: 41)) == .tooLong)
        #expect(problem(.landmark, String(repeating: "a", count: 201)) == .tooLong)
        #expect(problem(.caregiverName, String(repeating: "a", count: 121)) == .tooLong)
        #expect(problem(.relation, String(repeating: "a", count: 61)) == .tooLong)
    }

    @Test func `a number is a plus and eight to fifteen digits`() {
        for ok in [
            "0722 123 456", "0722-123-456", "+40 256 123 456", "0040722123456", "722123456",
            "+4930123456",
        ] {
            #expect(isPhone(ok), "\(ok)")
        }
        for bad in ["", "07", "0722 12", "abc", "+4072212345678901", "0722 abc 456"] {
            #expect(!isPhone(bad), "\(bad)")
        }
        #expect(
            problems(step1.merging([.phone: "07"]) { $1 }, Step.senior.fields, draft: true)[.phone]
                == .notAPhone)
    }

    @Test func `a draft may leave the street and number empty but not later`() {
        #expect(problems(step1, Step.address.fields, draft: true).isEmpty)
        #expect(
            problems(step1, Step.address.fields, draft: false) == [
                .street: .required, .streetNumber: .required,
            ])
        #expect(problems(all, Step.address.fields, draft: false).isEmpty)
    }

    @Test func `continue is enabled when the step is valid`() {
        #expect(!canContinue(.senior, [:], draft: true))
        #expect(!canContinue(.senior, step1.filter { $0.key != .phone }, draft: true))
        #expect(canContinue(.senior, step1, draft: true))
        #expect(canContinue(.address, step1, draft: true))
        #expect(!canContinue(.address, step1, draft: false))
        // Step 3 sends nothing; step 4 has its own button
        #expect(canContinue(.caregivers, [:], draft: true))
        #expect(!canContinue(.review, all, draft: true))
    }

    @Test func `the body is trimmed with empty fields as null`() {
        let typed: [Field: String] = [
            .fullName: "  Maria Popescu ", .formOfAddress: "doamna Maria",
            .phone: " 0722 123 456 ", .street: "", .block: "   ",
        ]
        #expect(
            bodyOf(typed)
                == SeniorForm(
                    fullName: "Maria Popescu", formOfAddress: "doamna Maria", phone: "+40722123456",
                    callWindow: nil, street: nil, streetNumber: nil, block: nil, staircase: nil,
                    floor: nil, apartment: nil, intercomCode: nil, keyHolder: nil, landmark: nil))
    }

    @Test func `the body names every field of the registration and sends its nulls`() throws {
        // PUT replaces every field, so a field left out would be emptied (seniors §3.5)
        let data = try ApiClient.makeEncoder().encode(bodyOf(step1))
        let json = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(Set(json.keys) == Set(REGISTRATION.map(\.key)))
        #expect(json["street"] is NSNull)
    }

    private let page = SeniorPage(
        id: "s1", fullName: "Maria Popescu", formOfAddress: "doamna Maria", phone: "+40256123456",
        landline: true, state: "submitted", street: "Str. Daliei", streetNumber: "12", block: "B3",
        staircase: "A", floor: "2", apartment: "9", intercomCode: "09",
        keyHolder: "vecina de la ap. 10", landmark: "lângă farmacie", callWindow: "9-12",
        medic: Medic(displayName: "Dr. Ion Pop"),
        caregivers: [
            Caregiver(userId: "u1", displayName: "Ioana Pop", relation: "fiică", phone: "+40700000004")
        ])

    @Test func `a saved senior fills the form`() {
        let values = valuesOf(page)
        var landline = page
        landline.phone = "+40212345678"
        #expect(valuesOf(landline)[.phone] == "021 234 5678")
        #expect(values[.phone] == "0256 123 456")
        // Saving again without a change sends what was saved
        #expect(bodyOf(values) == body)
        var noBlock = page
        noBlock.block = nil
        #expect(valuesOf(noBlock)[.block] == "")
    }

    @Test func `step 1 creates the senior the first time and saves after that`() {
        #expect(saveFor(.senior, id: nil, step1) == .create(bodyOf(step1)))
        #expect(saveFor(.senior, id: "s1", step1) == .update(id: "s1", bodyOf(step1)))
    }

    @Test func `step 2 sends the whole registration`() {
        #expect(saveFor(.address, id: "s1", all) == .update(id: "s1", body))
    }

    @Test func `step 3 sends nothing`() {
        // „Adaugă” and „Elimină” call the API at once (seniors §9.2)
        #expect(saveFor(.caregivers, id: "s1", all) == Save.none)
        #expect(saveFor(.review, id: "s1", all) == Save.none)
    }

    @Test func `a caregiver is trimmed with the number as E164`() {
        let typed: [Field: String] = [
            .caregiverName: " Ioana Pop ", .relation: "fiică ", .caregiverPhone: "0700 000 004",
        ]
        #expect(
            caregiverOf(typed) == CaregiverForm(displayName: "Ioana Pop", relation: "fiică", phone: "+40700000004"))
        #expect(problems(typed, Step.caregivers.fields, draft: true).isEmpty)
        #expect(
            Set(problems([:], Step.caregivers.fields, draft: true).keys) == [
                .caregiverName, .relation, .caregiverPhone,
            ])
    }

    @Test func `submitting needs the street its number and a caregiver`() {
        #expect(missingOf(page) == [])
        var bare = page
        bare.street = nil
        bare.streetNumber = " "
        bare.caregivers = []
        #expect(missingOf(bare) == ["street", "street_number", "caregiver"])
        // Every name the server sends in `missing` has a label (04 §2)
        #expect(
            MISSING_LABELS == [
                "street": "field_street", "street_number": "field_street_number",
                "caregiver": "missing_caregiver",
            ])
    }

    @Test func `the steps are in order`() {
        #expect(
            Step.allCases.map(\.title) == ["step_senior", "step_address", "step_caregivers", "step_review"])
        #expect(Step.senior.next == .address)
        #expect(Step.address.previous == .senior)
    }

    // Every label the form shows is in the catalog
    @Test func `every field label and step title is a Romanian string`() {
        for field in Field.allCases {
            #expect(String(localized: String.LocalizationValue(field.label)) != field.label, "\(field)")
        }
        for step in Step.allCases {
            #expect(String(localized: String.LocalizationValue(step.title)) != step.title, "\(step)")
        }
    }
}
