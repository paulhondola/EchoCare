import AVFAudio
import SwiftUI

/// „Sunteți bine?”, after `AreYouOkScreen.kt` and redesigned for seniors (design 2026-11-14, watch
/// senior UI): shown when the fall detector or an anomaly rule fires (UC-09). The senior has 15 s in
/// the demo, 2 min in production, to say they are fine; „Nu” or silence sends the event and starts
/// a call. Two big buttons fill the screen, an amber ring around the edge drains as the time runs
/// out, the watch asks the question aloud when it has a Romanian voice, and a double tap answers
/// „Da”. `Monitor` owns the deadline and the one outcome per prompt; this only shows it.
struct AreYouOkView: View {
    let prompt: Prompt
    let answer: (Bool) -> Void

    var body: some View {
        ZStack {
            TimelineView(.periodic(from: .now, by: 0.5)) { context in
                RoundedRectangle(cornerRadius: 40, style: .continuous)
                    .trim(from: 0, to: prompt.remainingFraction(nowMs: ms(context.date)))
                    .stroke(Palette.ring, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .ignoresSafeArea()
            }
            .accessibilityHidden(true)
            // Large text sizes scroll rather than push the buttons off the screen
            ViewThatFits(in: .vertical) {
                content(stretch: true)
                ScrollView { content(stretch: false) }
            }
            .padding(.horizontal, 8)
        }
        .onAppear { PromptVoice.speak() }
    }

    private func content(stretch: Bool) -> some View {
        VStack(spacing: 6) {
            Text("are_you_ok_title")
                .font(.title3.weight(.heavy))
                .multilineTextAlignment(.center)
            choice("are_you_ok_yes", symbol: "checkmark", fill: Palette.yes, stretch: stretch) {
                answer(true)
            }
            .handGestureShortcut(.primaryAction)
            choice("are_you_ok_no", symbol: "xmark", fill: Palette.help, stretch: stretch) {
                answer(false)
            }
        }
    }

    private func choice(
        _ title: LocalizedStringKey, symbol: String, fill: Color, stretch: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Label(title, systemImage: symbol)
                .font(.headline)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, maxHeight: stretch ? .infinity : nil)
        }
        .buttonStyle(.borderedProminent)
        .tint(fill)
    }

    private func ms(_ date: Date) -> Int64 {
        Int64(date.timeIntervalSince1970 * 1_000)
    }
}

/// Says „Sunteți bine?” once, only with a Romanian voice: a wrong-language voice would confuse more
/// than help. The workout session owns the audio, so the audio session is left alone.
@MainActor
private enum PromptVoice {
    static let synthesizer = AVSpeechSynthesizer()

    static func speak() {
        guard let voice = AVSpeechSynthesisVoice(language: "ro-RO") else { return }
        let utterance = AVSpeechUtterance(string: String(localized: "are_you_ok_title"))
        utterance.voice = voice
        synthesizer.speak(utterance)
    }
}
