import SwiftUI

/// „Sunteți bine?”, ported from `AreYouOkScreen.kt`: shown when the fall detector or an anomaly rule
/// fires (UC-09). The senior has 15 s in the demo, 2 min in production, to say they are fine;
/// „Nu” or silence sends the event and starts a call. The countdown is only shown here: `Monitor`
/// owns the deadline and the one outcome per prompt.
struct AreYouOkView: View {
    let prompt: Prompt
    let answer: (Bool) -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Text("are_you_ok_title")
                    .font(.headline)
                TimelineView(.periodic(from: .now, by: 0.5)) { context in
                    Text(verbatim: countdown(at: context.date))
                        .font(.title2.monospacedDigit())
                        .frame(maxWidth: .infinity)
                }
                Button("are_you_ok_yes") { answer(true) }
                Button("are_you_ok_no") { answer(false) }
                    .tint(.red)
            }
        }
    }

    private func countdown(at date: Date) -> String {
        let nowMs = Int64(date.timeIntervalSince1970 * 1_000)
        let remainingS = max(0, prompt.deadlineMs - nowMs) / 1_000
        return String(format: String(localized: "are_you_ok_countdown"), remainingS)
    }
}
