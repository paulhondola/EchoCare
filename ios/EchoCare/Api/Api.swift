import Foundation

// The FastAPI contract's payloads (04-interfaces.md), one type per Kotlin data class in
// android/app/src/main/java/ro/echocare/Api.kt, with the same names, optionality and defaults.
// `ApiClient`'s coders convert snake_case, so a `CodingKeys` raw value is the camelCase form of the
// wire key (`phone_e164` is `phoneE164`). Enum-like values stay `String`s: a later server may add one
// (ADR-001 §2.3), and unknown top-level keys are ignored by `JSONDecoder`. Dates stay `String`s too.

extension KeyedDecodingContainer {
    /// A key the server may omit or send as null, read as [fallback] (Kotlin's default value).
    func value<T: Decodable>(_ key: Key, default fallback: T) throws -> T {
        try decodeIfPresent(T.self, forKey: key) ?? fallback
    }
}

// GET /profile (auth-layer §3.3). Only the fields the app reads; roles stay strings.
// [warningActive]: a weather warning is in force, shown on the senior's home (Q5).
struct Me: Codable, Equatable, Sendable {
    var displayName: String
    var grants: [Grant]
    var warningActive: Bool = false

    enum CodingKeys: String, CodingKey { case displayName, grants, warningActive }

    init(displayName: String, grants: [Grant], warningActive: Bool = false) {
        self.displayName = displayName
        self.grants = grants
        self.warningActive = warningActive
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        displayName = try c.decode(String.self, forKey: .displayName)
        grants = try c.decode([Grant].self, forKey: .grants)
        warningActive = try c.value(.warningActive, default: false)
    }
}

struct Grant: Codable, Equatable, Sendable {
    var role: String
}

// One row of GET /seniors (seniors §3.3). The state stays a string.
// [code], [reason] and [since] are the latest result of an active senior, else nil (03 §8).
struct SeniorRow: Codable, Equatable, Sendable {
    var id: String
    var fullName: String
    var formOfAddress: String
    var phone: String
    var landline: Bool
    var state: String
    var code: String?
    var reason: String?
    var since: String?
    // When the registration was made, sent to DAS and accepted (04 §1). [watchState] is ok,
    // not_worn or offline, a string for a later server's value (UC-12).
    var createdAt: String?
    var submittedAt: String?
    var acceptedAt: String?
    var watchState: String?
    // The medical record's state for the registering medic, nil for anyone else.
    var medicalRecordState: String?

    enum CodingKeys: String, CodingKey {
        case id, fullName, formOfAddress
        case phone = "phoneE164"
        case landline = "phoneIsLandline"
        case state = "enrollmentState"
        case code, reason, since, createdAt, submittedAt, acceptedAt, watchState, medicalRecordState
    }
}

// GET /seniors/{id} (seniors §3.3): the row, the address with its access details (G13), the medic
// and the caregivers. The same for every role (seniors SE7).
struct SeniorPage: Codable, Equatable, Sendable {
    var id: String
    var fullName: String
    var formOfAddress: String
    var phone: String
    var landline: Bool
    var state: String
    var code: String?
    var reason: String?
    var since: String?
    var street: String?
    var streetNumber: String?
    var block: String?
    var staircase: String?
    var floor: String?
    var apartment: String?
    var intercomCode: String?
    var keyHolder: String?
    var landmark: String?
    var callWindow: String?
    var medic: Medic
    var caregivers: [Caregiver] = []
    // One of her calls is ringing or live (UC-12). Nil from an older API, which reads as no.
    var callInProgress: Bool?
    // The watch's state and latest pulse (UC-03, UC-12). Nil before the first check-in or for DAS.
    var watchState: String?
    var lastPulse: Int?
    // What the medic declared, nil when not stated, and whether her own phone's app has ever
    // signed in; both nil from an older API (UC-13, design 2026-11-14).
    var equipment: [String]?
    var appSignedIn: Bool?
    // Whether the home node has sent a room reading (04 §1, P20); this app shows only that much.
    var hasRoom = false
    // The timeline of the registration and of her consent (04 §1, G7); all nil from an older API.
    var createdAt: String?
    var submittedAt: String?
    var acceptedAt: String?
    var consent: ConsentState?
    var consentGivenAt: String?
    var signedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, fullName, formOfAddress
        case phone = "phoneE164"
        case landline = "phoneIsLandline"
        case state = "enrollmentState"
        case code, reason, since, street, streetNumber, block, staircase, floor, apartment
        case intercomCode, keyHolder, landmark, callWindow, medic, caregivers, callInProgress
        case watchState, lastPulse, createdAt, submittedAt, acceptedAt, consent, consentGivenAt
        case signedAt, equipment, appSignedIn
    }

    // Read on its own: only whether it is there, so it stays out of the encoded keys
    private enum RoomKey: String, CodingKey { case room }

    init(
        id: String, fullName: String, formOfAddress: String, phone: String, landline: Bool,
        state: String, code: String? = nil, reason: String? = nil, since: String? = nil,
        street: String? = nil, streetNumber: String? = nil, block: String? = nil,
        staircase: String? = nil, floor: String? = nil, apartment: String? = nil,
        intercomCode: String? = nil, keyHolder: String? = nil, landmark: String? = nil,
        callWindow: String? = nil, medic: Medic, caregivers: [Caregiver] = [],
        callInProgress: Bool? = nil, watchState: String? = nil, lastPulse: Int? = nil,
        createdAt: String? = nil, submittedAt: String? = nil, acceptedAt: String? = nil,
        consent: ConsentState? = nil, consentGivenAt: String? = nil, signedAt: String? = nil
    ) {
        self.id = id
        self.fullName = fullName
        self.formOfAddress = formOfAddress
        self.phone = phone
        self.landline = landline
        self.state = state
        self.code = code
        self.reason = reason
        self.since = since
        self.street = street
        self.streetNumber = streetNumber
        self.block = block
        self.staircase = staircase
        self.floor = floor
        self.apartment = apartment
        self.intercomCode = intercomCode
        self.keyHolder = keyHolder
        self.landmark = landmark
        self.callWindow = callWindow
        self.medic = medic
        self.caregivers = caregivers
        self.callInProgress = callInProgress
        self.watchState = watchState
        self.lastPulse = lastPulse
        self.createdAt = createdAt
        self.submittedAt = submittedAt
        self.acceptedAt = acceptedAt
        self.consent = consent
        self.consentGivenAt = consentGivenAt
        self.signedAt = signedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        fullName = try c.decode(String.self, forKey: .fullName)
        formOfAddress = try c.decode(String.self, forKey: .formOfAddress)
        phone = try c.decode(String.self, forKey: .phone)
        landline = try c.decode(Bool.self, forKey: .landline)
        state = try c.decode(String.self, forKey: .state)
        code = try c.decodeIfPresent(String.self, forKey: .code)
        reason = try c.decodeIfPresent(String.self, forKey: .reason)
        since = try c.decodeIfPresent(String.self, forKey: .since)
        street = try c.decodeIfPresent(String.self, forKey: .street)
        streetNumber = try c.decodeIfPresent(String.self, forKey: .streetNumber)
        block = try c.decodeIfPresent(String.self, forKey: .block)
        staircase = try c.decodeIfPresent(String.self, forKey: .staircase)
        floor = try c.decodeIfPresent(String.self, forKey: .floor)
        apartment = try c.decodeIfPresent(String.self, forKey: .apartment)
        intercomCode = try c.decodeIfPresent(String.self, forKey: .intercomCode)
        keyHolder = try c.decodeIfPresent(String.self, forKey: .keyHolder)
        landmark = try c.decodeIfPresent(String.self, forKey: .landmark)
        callWindow = try c.decodeIfPresent(String.self, forKey: .callWindow)
        medic = try c.decode(Medic.self, forKey: .medic)
        caregivers = try c.value(.caregivers, default: [])
        callInProgress = try c.decodeIfPresent(Bool.self, forKey: .callInProgress)
        watchState = try c.decodeIfPresent(String.self, forKey: .watchState)
        lastPulse = try c.decodeIfPresent(Int.self, forKey: .lastPulse)
        createdAt = try c.decodeIfPresent(String.self, forKey: .createdAt)
        submittedAt = try c.decodeIfPresent(String.self, forKey: .submittedAt)
        acceptedAt = try c.decodeIfPresent(String.self, forKey: .acceptedAt)
        consent = try c.decodeIfPresent(ConsentState.self, forKey: .consent)
        consentGivenAt = try c.decodeIfPresent(String.self, forKey: .consentGivenAt)
        signedAt = try c.decodeIfPresent(String.self, forKey: .signedAt)
        equipment = try c.decodeIfPresent([String].self, forKey: .equipment)
        appSignedIn = try c.decodeIfPresent(Bool.self, forKey: .appSignedIn)
        let r = try decoder.container(keyedBy: RoomKey.self)
        hasRoom = try r.contains(.room) && !r.decodeNil(forKey: .room)
    }
}

// Her latest consent decision (04 §1). Decision and method stay strings. [at] is ISO-8601.
struct ConsentState: Codable, Equatable, Sendable {
    var decision: String
    var method: String
    var at: String
}

// POST /seniors/{id}/signature's body (04 §2): the consent text's version and the strokes of the
// signature, each a list of [x, y] points.
struct SignatureForm: Codable, Equatable, Sendable {
    var textVersion: String
    var strokes: [[[Float]]]
}

// One row of GET /seniors/{id}/calls (04 §1), newest first. No turns, no transcript (01 §6).
struct CallRow: Codable, Equatable, Sendable {
    var id: String
    var trigger: String
    var state: String
    var dueAt: String
    var startedAt: String?
    var endedAt: String?
    var finalSeverity: String?
    var reason: String?
}

struct Medic: Codable, Equatable, Sendable {
    var displayName: String
    var practice: String?
}

struct Caregiver: Codable, Equatable, Sendable {
    var userId: String
    var displayName: String
    var relation: String?
    var phone: String

    enum CodingKeys: String, CodingKey {
        case userId, displayName, relation
        case phone = "phoneE164"
    }
}

// POST /seniors and PUT /seniors/{id}'s body: the whole registration (seniors §3.5). Every field is
// sent, an empty one as null: PUT replaces every field.
struct SeniorForm: Codable, Equatable, Sendable {
    var fullName: String
    var formOfAddress: String
    var phone: String
    var callWindow: String?
    var street: String?
    var streetNumber: String?
    var block: String?
    var staircase: String?
    var floor: String?
    var apartment: String?
    var intercomCode: String?
    var keyHolder: String?
    var landmark: String?
    // smartphone, watch, home_node as the medic ticked them; nil is left out, so the server keeps
    // what it holds (design 2026-11-14)
    var equipment: [String]? = nil

    enum CodingKeys: String, CodingKey {
        case fullName, formOfAddress, phone, callWindow, street, streetNumber, block, staircase
        case floor, apartment, intercomCode, keyHolder, landmark, equipment
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(fullName, forKey: .fullName)
        try c.encode(formOfAddress, forKey: .formOfAddress)
        try c.encode(phone, forKey: .phone)
        // `encode` on an optional writes null, where the synthesized encoder would omit the key.
        try c.encode(callWindow, forKey: .callWindow)
        try c.encode(street, forKey: .street)
        try c.encode(streetNumber, forKey: .streetNumber)
        try c.encode(block, forKey: .block)
        try c.encode(staircase, forKey: .staircase)
        try c.encode(floor, forKey: .floor)
        try c.encode(apartment, forKey: .apartment)
        try c.encode(intercomCode, forKey: .intercomCode)
        try c.encode(keyHolder, forKey: .keyHolder)
        try c.encode(landmark, forKey: .landmark)
        try c.encodeIfPresent(equipment, forKey: .equipment)
    }
}

// POST /seniors/{id}/caregivers's body (seniors §3.5). The phone must be a mobile.
struct CaregiverForm: Codable, Equatable, Sendable {
    var displayName: String
    var relation: String
    var phone: String
}

// The medical record (design §5.7): [state] stays a string. [items] is nil until analysed;
// [pdfUrl] is presigned for 10 minutes.
struct MedicalItem: Codable, Equatable, Sendable {
    var condition: String
    var question: String
    var worrying: String
    var evidence: String = ""
    var included: Bool = true

    enum CodingKeys: String, CodingKey { case condition, question, worrying, evidence, included }

    init(
        condition: String, question: String, worrying: String, evidence: String = "",
        included: Bool = true
    ) {
        self.condition = condition
        self.question = question
        self.worrying = worrying
        self.evidence = evidence
        self.included = included
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        condition = try c.decode(String.self, forKey: .condition)
        question = try c.decode(String.self, forKey: .question)
        worrying = try c.decode(String.self, forKey: .worrying)
        evidence = try c.value(.evidence, default: "")
        included = try c.value(.included, default: true)
    }
}

struct MedicalRecord: Codable, Equatable, Sendable {
    var state: String
    var uploadedAt: String
    var analyzedAt: String?
    var confirmedAt: String?
    var items: [MedicalItem]?
    var pdfUrl: String?
}

// [worrying] nil keeps the stored one.
struct ConfirmItem: Codable, Equatable, Sendable {
    var included: Bool
    var question: String
    var worrying: String?
}

// [analyzedAt] is the profile the medic reviewed.
struct MedicalConfirmForm: Codable, Equatable, Sendable {
    var items: [ConfirmItem]
    var analyzedAt: String?
}

// GET /profile/mock-call (design §4.2): the senior's due call, which the card answers in place of a
// phone. [trigger] stays a string. [kind] and [level] are a campaign's, [consentText] a welcome
// call's, shown as the server sent it.
struct MockCall: Codable, Equatable, Sendable {
    var callId: String
    var trigger: String
    var kind: String?
    var level: String?
    var consentText: String?

    enum CodingKeys: String, CodingKey {
        case callId, trigger
        case kind = "campaignKind"
        case level = "campaignLevel"
        case consentText
    }
}

// POST /calls/{id}/mock-answer's body (design §4.2), one shape per trigger. The defaults are not
// sent: a campaign answer is the three choices or [declined], a welcome answer is [consent].
struct MockAnswer: Codable, Equatable, Sendable {
    var feeling: String?
    var day: String?
    var shelter: String?
    var declined: Bool = false
    var consent: Bool?

    enum CodingKeys: String, CodingKey { case feeling, day, shelter, declined, consent }

    init(
        feeling: String? = nil, day: String? = nil, shelter: String? = nil, declined: Bool = false,
        consent: Bool? = nil
    ) {
        self.feeling = feeling
        self.day = day
        self.shelter = shelter
        self.declined = declined
        self.consent = consent
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        feeling = try c.decodeIfPresent(String.self, forKey: .feeling)
        day = try c.decodeIfPresent(String.self, forKey: .day)
        shelter = try c.decodeIfPresent(String.self, forKey: .shelter)
        declined = try c.value(.declined, default: false)
        consent = try c.decodeIfPresent(Bool.self, forKey: .consent)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(feeling, forKey: .feeling)
        try c.encodeIfPresent(day, forKey: .day)
        try c.encodeIfPresent(shelter, forKey: .shelter)
        if declined { try c.encode(declined, forKey: .declined) }
        try c.encodeIfPresent(consent, forKey: .consent)
    }
}

// POST /me/check-ins' body (04 §3, UC-13). 204, no body.
struct CheckInForm: Codable, Equatable, Sendable {
    var measuredAt: String
    var battery: Int?
    var worn: Bool?
    var lastPulse: Int?
    var restingPulse: Int?
    var stepsToday: Int?
    var minutesWithoutSteps: Int?

    init(
        measuredAt: String, battery: Int? = nil, worn: Bool? = nil, lastPulse: Int? = nil,
        restingPulse: Int? = nil, stepsToday: Int? = nil, minutesWithoutSteps: Int? = nil
    ) {
        self.measuredAt = measuredAt
        self.battery = battery
        self.worn = worn
        self.lastPulse = lastPulse
        self.restingPulse = restingPulse
        self.stepsToday = stepsToday
        self.minutesWithoutSteps = minutesWithoutSteps
    }
}

// POST /me/health-readings' body (04 §3): one Apple Health blood oxygen or ECG reading. [id] is
// the HealthKit sample's UUID, so a resend is a duplicate. [kind] is spo2 or ecg; [ecgTrace] is
// microvolts at [ecgTraceHz]. 204, no body.
struct HealthReadingForm: Codable, Equatable, Sendable {
    var id: String
    var kind: String
    var measuredAt: String
    var spo2: Int?
    var ecgClassification: String?
    var ecgHeartRate: Int?
    var ecgTrace: [Int]?
    var ecgTraceHz: Int?

    init(
        id: String, kind: String, measuredAt: String, spo2: Int? = nil,
        ecgClassification: String? = nil, ecgHeartRate: Int? = nil, ecgTrace: [Int]? = nil,
        ecgTraceHz: Int? = nil
    ) {
        self.id = id
        self.kind = kind
        self.measuredAt = measuredAt
        self.spo2 = spo2
        self.ecgClassification = ecgClassification
        self.ecgHeartRate = ecgHeartRate
        self.ecgTrace = ecgTrace
        self.ecgTraceHz = ecgTraceHz
    }
}

// POST /me/events' body (04 §3). [type] is one of manual_request, fall, high_pulse_at_rest,
// inactivity; [measuredAt] is ISO-8601 with an offset; [id] is the device's, so a resend is a
// duplicate. [source] is watch, phone or home_node.
struct EventForm: Codable, Equatable, Sendable {
    var id: String
    var type: String
    var measuredAt: String
    var source: String?
    var snapshot: EventSnapshotForm?
    var latitude: Double?
    var longitude: Double?
    var locationAccuracyM: Double?

    init(
        id: String, type: String, measuredAt: String, source: String? = nil,
        snapshot: EventSnapshotForm? = nil, latitude: Double? = nil, longitude: Double? = nil,
        locationAccuracyM: Double? = nil
    ) {
        self.id = id
        self.type = type
        self.measuredAt = measuredAt
        self.source = source
        self.snapshot = snapshot
        self.latitude = latitude
        self.longitude = longitude
        self.locationAccuracyM = locationAccuracyM
    }
}

struct EventSnapshotForm: Codable, Equatable, Sendable {
    var pulse: Int?
    var restingBaseline: Int?
    var moving: Bool?
    var minutesWithoutSteps: Int?
    var battery: Int?

    init(
        pulse: Int? = nil, restingBaseline: Int? = nil, moving: Bool? = nil,
        minutesWithoutSteps: Int? = nil, battery: Int? = nil
    ) {
        self.pulse = pulse
        self.restingBaseline = restingBaseline
        self.moving = moving
        self.minutesWithoutSteps = minutesWithoutSteps
        self.battery = battery
    }
}

// POST /me/events' answer: [queued] when this event queued a call, [callId] the call it started or
// joined, nil when no call was queued.
struct EventResult: Codable, Equatable, Sendable {
    var queued: Bool = false
    var callId: String?

    enum CodingKeys: String, CodingKey { case queued, callId }

    init(queued: Bool = false, callId: String? = nil) {
        self.queued = queued
        self.callId = callId
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        queued = try c.value(.queued, default: false)
        callId = try c.decodeIfPresent(String.self, forKey: .callId)
    }
}

// One row of GET /incidents (04 §1). [status] stays a string: a later server may add one.
struct IncidentRow: Codable, Equatable, Sendable {
    var id: String
    var seniorName: String
    var formOfAddress: String
    var status: String
    var reason: String
    var openedAt: String
    var takenByName: String?
    var takenAt: String?
    var handoverAnswered: Bool = false

    enum CodingKeys: String, CodingKey {
        case id
        case seniorName = "seniorFullName"
        case formOfAddress = "seniorFormOfAddress"
        case status, reason, openedAt, takenByName, takenAt, handoverAnswered
    }

    init(
        id: String, seniorName: String, formOfAddress: String, status: String, reason: String,
        openedAt: String, takenByName: String? = nil, takenAt: String? = nil,
        handoverAnswered: Bool = false
    ) {
        self.id = id
        self.seniorName = seniorName
        self.formOfAddress = formOfAddress
        self.status = status
        self.reason = reason
        self.openedAt = openedAt
        self.takenByName = takenByName
        self.takenAt = takenAt
        self.handoverAnswered = handoverAnswered
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        seniorName = try c.decode(String.self, forKey: .seniorName)
        formOfAddress = try c.decode(String.self, forKey: .formOfAddress)
        status = try c.decode(String.self, forKey: .status)
        reason = try c.decode(String.self, forKey: .reason)
        openedAt = try c.decode(String.self, forKey: .openedAt)
        takenByName = try c.decodeIfPresent(String.self, forKey: .takenByName)
        takenAt = try c.decodeIfPresent(String.self, forKey: .takenAt)
        handoverAnswered = try c.value(.handoverAnswered, default: false)
    }
}

// GET /incidents/{id} (04 §1): the senior with access details, the caregivers, the triggering event
// and every call from the first attempt until the incident was resolved.
struct IncidentPage: Codable, Equatable, Sendable {
    var id: String
    var status: String
    var reason: String
    var openedAt: String
    var takenByName: String?
    var handoverAnswered: Bool = false
    var senior: IncidentSenior
    var caregivers: [IncidentCaregiver] = []
    var event: TriggerEvent?
    var calls: [IncidentCall] = []

    enum CodingKeys: String, CodingKey {
        case id, status, reason, openedAt, takenByName, handoverAnswered, senior, caregivers
        case event, calls
    }

    init(
        id: String, status: String, reason: String, openedAt: String, takenByName: String? = nil,
        handoverAnswered: Bool = false, senior: IncidentSenior,
        caregivers: [IncidentCaregiver] = [], event: TriggerEvent? = nil,
        calls: [IncidentCall] = []
    ) {
        self.id = id
        self.status = status
        self.reason = reason
        self.openedAt = openedAt
        self.takenByName = takenByName
        self.handoverAnswered = handoverAnswered
        self.senior = senior
        self.caregivers = caregivers
        self.event = event
        self.calls = calls
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        status = try c.decode(String.self, forKey: .status)
        reason = try c.decode(String.self, forKey: .reason)
        openedAt = try c.decode(String.self, forKey: .openedAt)
        takenByName = try c.decodeIfPresent(String.self, forKey: .takenByName)
        handoverAnswered = try c.value(.handoverAnswered, default: false)
        senior = try c.decode(IncidentSenior.self, forKey: .senior)
        caregivers = try c.value(.caregivers, default: [])
        event = try c.decodeIfPresent(TriggerEvent.self, forKey: .event)
        calls = try c.value(.calls, default: [])
    }
}

struct IncidentSenior: Codable, Equatable, Sendable {
    var id: String
    var fullName: String
    var formOfAddress: String
    var phone: String
    var landline: Bool
    var street: String?
    var streetNumber: String?
    var block: String?
    var staircase: String?
    var floor: String?
    var apartment: String?
    var intercomCode: String?
    var keyHolder: String?
    var landmark: String?

    enum CodingKeys: String, CodingKey {
        case id, fullName, formOfAddress
        case phone = "phoneE164"
        case landline = "phoneIsLandline"
        case street, streetNumber, block, staircase, floor, apartment, intercomCode, keyHolder
        case landmark
    }
}

// No user id here, unlike GET /seniors/{id}'s Caregiver.
struct IncidentCaregiver: Codable, Equatable, Sendable {
    var displayName: String
    var phone: String
    var relation: String?

    enum CodingKeys: String, CodingKey {
        case displayName
        case phone = "phoneE164"
        case relation
    }
}

struct TriggerEvent: Codable, Equatable, Sendable {
    var type: String
    var measuredAt: String
    var latitude: Double?
    var longitude: Double?
    var accuracy: Double?

    enum CodingKeys: String, CodingKey {
        case type, measuredAt, latitude, longitude
        case accuracy = "locationAccuracyM"
    }
}

// [handoverAnswered] is nil when no hand-over was tried on this call.
struct IncidentCall: Codable, Equatable, Sendable {
    var id: String
    var trigger: String
    var attempt: Int
    var state: String
    var startedAt: String?
    var finalSeverity: String?
    var handoverAnswered: Bool?
    var reports: [CallReport] = []
    var turns: [CallTurn] = []
    // GET /calls/{id}/transcript only (04 §1); none on the incident page or from an older server
    var answers: [CallAnswer] = []

    enum CodingKeys: String, CodingKey {
        case id, trigger, attempt, state, startedAt, finalSeverity, handoverAnswered, reports
        case turns, answers
    }

    init(
        id: String, trigger: String, attempt: Int, state: String, startedAt: String? = nil,
        finalSeverity: String? = nil, handoverAnswered: Bool? = nil, reports: [CallReport] = [],
        turns: [CallTurn] = [], answers: [CallAnswer] = []
    ) {
        self.id = id
        self.trigger = trigger
        self.attempt = attempt
        self.state = state
        self.startedAt = startedAt
        self.finalSeverity = finalSeverity
        self.handoverAnswered = handoverAnswered
        self.reports = reports
        self.turns = turns
        self.answers = answers
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        trigger = try c.decode(String.self, forKey: .trigger)
        attempt = try c.decode(Int.self, forKey: .attempt)
        state = try c.decode(String.self, forKey: .state)
        startedAt = try c.decodeIfPresent(String.self, forKey: .startedAt)
        finalSeverity = try c.decodeIfPresent(String.self, forKey: .finalSeverity)
        handoverAnswered = try c.decodeIfPresent(Bool.self, forKey: .handoverAnswered)
        reports = try c.value(.reports, default: [])
        turns = try c.value(.turns, default: [])
        answers = try c.value(.answers, default: [])
    }
}

// One answer the call heard (05 §2): [field] stays a string, so a question added later decodes.
struct CallAnswer: Codable, Equatable, Sendable {
    var field: String
    var value: String
    var clear: Bool
    var quote: String
    var at: String
}

struct CallReport: Codable, Equatable, Sendable {
    var severity: String
    var reason: String
    var quote: String?
    var at: String
}

// [kind] is `speech` or `keys`, a key press whose [content] is the key.
struct CallTurn: Codable, Equatable, Sendable {
    var speaker: String
    var content: String
    var at: String
    var kind: String = "speech"

    enum CodingKeys: String, CodingKey { case speaker, content, at, kind }

    init(speaker: String, content: String, at: String, kind: String = "speech") {
        self.speaker = speaker
        self.content = content
        self.at = at
        self.kind = kind
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        speaker = try c.decode(String.self, forKey: .speaker)
        content = try c.decode(String.self, forKey: .content)
        at = try c.decode(String.self, forKey: .at)
        kind = try c.value(.kind, default: "speech")
    }
}

// POST /incidents/{id}/resolve's body (04 §2): both required, the note 1 to 1000 characters.
struct Resolution: Codable, Equatable, Sendable {
    var outcome: String
    var note: String
}
