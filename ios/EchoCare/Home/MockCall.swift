import Foundation
import SwiftUI

// The mock call card's logic (design §6.2): the senior answers on the phone's screen what a call
// would ask. Campaign calls ask three questions (Q8); the welcome call asks for consent (Q11).
// Ported from android/app/.../home/MockCall.kt. Pure, tested.

/// The days the server reads (design §4.2), in the order of the day buttons.
let DAYS = ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"]

/// A choice: the value the server reads, and its `Localizable.xcstrings` key.
struct Choice: Equatable, Sendable {
    let value: String
    let label: String
}

// What the buttons send: the server's values for each answer, "unknown" for „Nu știu”.
let FEELINGS = [Choice(value: "ok", label: "feeling_ok"), Choice(value: "unwell", label: "feeling_unwell")]
let DAY_CHOICES =
    zip(
        DAYS,
        ["day_luni", "day_marti", "day_miercuri", "day_joi", "day_vineri", "day_sambata", "day_duminica"]
    ).map { Choice(value: $0, label: $1) } + [Choice(value: "unknown", label: "day_unknown")]
let SHELTERS = [Choice(value: "yes", label: "yes"), Choice(value: "no", label: "no")]

/// The body of „Trimite răspunsurile”: nil until all three questions are answered (Q8).
func campaignAnswer(feeling: String?, day: String?, shelter: String?) -> MockAnswer? {
    guard let feeling, let day, let shelter else { return nil }
    return MockAnswer(feeling: feeling, day: day, shelter: shelter)
}

/// The card after a read that answered `status` (nil: no answer at all). Only the server's own
/// answer changes it: 200 is `body`, and 204 (nothing due), 403 and 404 (production) are no card.
/// A lost connection or a 5xx, say a redeploy, keeps `previous` so the senior's choices survive
/// (design §6.2).
func cardAfterRead(status: Int?, body: MockCall?, previous: MockCall?) -> MockCall? {
    switch status {
    case 200: body
    case 204, 403, 404: nil
    default: previous
    }
}

/// Whether a post that answered `status` (nil: no answer at all) is done with the card: the server
/// took it (2xx) or refused it (4xx, a 409 and a 422 included), so the page rereads. Otherwise the
/// answer may not have arrived, and the card stays for the senior to press again (design §6.2).
func answerSettled(status: Int?) -> Bool {
    guard let status else { return false }
    return (200...499).contains(status)
}

// ApiClient returns a card or nil (204, and 404) and throws ApiError.http for any other non-2xx; a
// lost connection throws a URLError. Android's functions above read the raw status, so these turn
// one into the other.

/// A read of the card as Android's `cardAfterRead` takes it.
struct MockRead: Equatable, Sendable {
    let status: Int?
    let body: MockCall?
}

/// Runs the read: a card is 200, none is 204 (ApiClient folds 404 into it, and both mean no card),
/// a refusal its own status, and anything else (no connection, a cancel) no answer at all.
func readMock(_ call: @Sendable () async throws -> MockCall?) async -> MockRead {
    do {
        if let card = try await call() { return MockRead(status: 200, body: card) }
        return MockRead(status: 204, body: nil)
    } catch {
        return MockRead(status: statusOf(error), body: nil)
    }
}

/// Runs the post: 204 once the server took it, a refusal its own status, else no answer at all.
func postStatus(_ call: @Sendable () async throws -> Void) async -> Int? {
    do {
        try await call()
        return 204
    } catch {
        return statusOf(error)
    }
}

// MARK: The card

private let EVENT_TRIGGERS = ["watch", "manual"]

/// The campaign's code and its kind as „Cod galben de caniculă”, or why a watch or „Sunați-mă” call
/// rings (UC-09, UC-10); nil for a value this build lacks.
private func warningLine(_ call: MockCall) -> String? {
    if EVENT_TRIGGERS.contains(call.trigger) { return String(localized: "mock_why_event") }
    let level =
        switch call.level {
        case "yellow": "level_yellow"
        case "red": "level_red"
        default: nil as String?
        }
    let kind =
        switch call.kind {
        case "cold": "kind_cold"
        case "heat": "kind_heat"
        default: nil as String?
        }
    guard let level, let kind else { return nil }
    return String(format: String(localized: "mock_warning"), String(localized: .init(level)), String(localized: .init(kind)))
}

/// `onAnswer` gets the body to post: the three choices, `declined`, or the consent.
struct MockCallCard: View {
    let call: MockCall
    let onAnswer: (MockAnswer) -> Void

    var body: some View {
        let welcome = call.trigger == "welcome"
        let tone: Tone = welcome ? .link : call.level == "red" ? .rosu : .galben
        VStack(alignment: .leading, spacing: 16) {
            Banner("mock_calling", tone: tone)
            if !welcome, let line = warningLine(call) {
                Text(verbatim: line).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
            }
            Text("mock_note").textStyle(Theme.bodyMedium).foregroundStyle(Theme.fgMuted)
            if welcome {
                Welcome(call: call, onAnswer: onAnswer)
            } else {
                // A new call starts with nothing chosen
                Campaign(call: call, onAnswer: onAnswer).id(call.callId)
            }
            Rule()
        }
        .padding(.bottom, 24)
    }
}

private struct Campaign: View {
    let call: MockCall
    let onAnswer: (MockAnswer) -> Void

    @State private var feeling: String?
    @State private var day: String?
    @State private var shelter: String?

    var body: some View {
        Question("q_feeling", FEELINGS, chosen: feeling) { feeling = $0 }
        Question("q_day", DAY_CHOICES, chosen: day) { day = $0 }
        Question(call.kind == "heat" ? "q_shelter_heat" : "q_shelter_cold", SHELTERS, chosen: shelter) {
            shelter = $0
        }
        let answer = campaignAnswer(feeling: feeling, day: day, shelter: shelter)
        SnButton("mock_send", kind: .success, fullWidth: true, minHeight: 56) {
            if let answer { onAnswer(answer) }
        }
        .disabled(answer == nil)
        SnButton("mock_later", kind: .outline, fullWidth: true, minHeight: 56) {
            onAnswer(MockAnswer(declined: true))
        }
    }
}

private struct Welcome: View {
    let call: MockCall
    let onAnswer: (MockAnswer) -> Void

    var body: some View {
        Text("welcome_title").textStyle(Theme.titleLarge).foregroundStyle(Theme.fg)
        if let text = call.consentText {
            Text(verbatim: text).textStyle(Theme.bodyLarge).foregroundStyle(Theme.fg)
        }
        // Equal buttons: neither answer is nudged
        WrappingRow(spacing: 8, lineSpacing: 8) {
            SnButton("yes", kind: .outline, minHeight: 56) { onAnswer(MockAnswer(consent: true)) }
            SnButton("no", kind: .outline, minHeight: 56) { onAnswer(MockAnswer(consent: false)) }
        }
    }
}

/// One question over its answers, each a large button; the `chosen` value is filled in.
private struct Question: View {
    let text: LocalizedStringKey
    let options: [Choice]
    let chosen: String?
    let onChoose: (String) -> Void

    init(_ text: LocalizedStringKey, _ options: [Choice], chosen: String?, onChoose: @escaping (String) -> Void) {
        self.text = text
        self.options = options
        self.chosen = chosen
        self.onChoose = onChoose
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(text).textStyle(Theme.titleMedium).foregroundStyle(Theme.fg)
            WrappingRow(spacing: 8, lineSpacing: 8) {
                ForEach(options, id: \.value) { option in
                    let picked = option.value == chosen
                    SnButton(LocalizedStringKey(option.label), kind: picked ? .success : .outline, minHeight: 56) {
                        onChoose(option.value)
                    }
                    .accessibilityAddTraits(picked ? .isSelected : [])
                }
            }
        }
    }
}
