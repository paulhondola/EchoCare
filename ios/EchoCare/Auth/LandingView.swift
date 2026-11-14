import SwiftUI

// The signed-out first screen: the system that watches and reacts on its own (UC-09, UC-07,
// UC-11), the dashboard's landing page folded to a phone. *Intrați* leads on to the phone step.
// Ported from android/app/.../auth/Landing.kt; the icons are SF Symbols in place of its drawables.

private let easeOut = (x1: 0.16, y1: 1.0, x2: 0.3, y2: 1.0)
private let stepMs = 900
private let holdMs = 4200

private func eased(_ seconds: Double) -> Animation {
    .timingCurve(easeOut.x1, easeOut.y1, easeOut.x2, easeOut.y2, duration: seconds)
}

/// One illustrative incident, as the web landing page plays it.
private let steps: [(at: String, key: String)] = [
    ("14:20:03", "landing_step_1"),
    ("14:20:04", "landing_step_2"),
    ("14:20:36", "landing_step_3"),
    ("14:20:58", "landing_step_4"),
    ("14:20:58", "landing_step_5"),
    ("14:21:01", "landing_step_6"),
]

/// The senior's own words, set brighter than the system's lines.
private let quotes: Set<String> = ["landing_step_4"]

private struct Does: Sendable {
    let symbol: String
    let tint: Color
    /// `Localizable.xcstrings` keys
    let title: String
    let text: String
}

private let does = [
    Does(
        symbol: "applewatch", tint: Theme.link, title: "landing_observe",
        text: "landing_observe_text"),
    Does(symbol: "phone", tint: Theme.fg, title: "landing_call", text: "landing_call_text"),
    Does(
        symbol: "scalemass", tint: Theme.rosuFg, title: "landing_decide",
        text: "landing_decide_text"),
    Does(
        symbol: "headphones", tint: Theme.verdeFg, title: "landing_hand_over",
        text: "landing_hand_over_text"),
]

// Landing.kt's one-off type sizes, on the Theme faces.
private let heroStyle = TextStyle(size: 36, lineHeight: 36, face: .extraBold, trackingEm: -0.035)
private let brandStyle = TextStyle(size: 15, lineHeight: 20, face: .extraBold)
private let doesTitleStyle = TextStyle(size: 16, lineHeight: 20, face: .extraBold)
private let bpmStyle = TextStyle(size: 20, lineHeight: nil, face: .monoMedium)
private let monoSmall = TextStyle(size: 11, lineHeight: nil, face: .monoMedium)
private let stepTimeStyle = TextStyle(size: 11, lineHeight: 18, face: .monoMedium)
private let liveStyle = TextStyle(size: 11, lineHeight: nil, face: .monoMedium, trackingEm: 0.04)
private let redStyle = TextStyle(size: 12, lineHeight: nil, face: .monoMedium, trackingEm: 0.05)
/// Landing.kt's `lerp(Palette.Fg, Palette.RosuFg, 0.35f)`: 0xF0F6FC a third of the way to 0xFF7B72.
private let redNote = Color(hex: 0xF5CBCC)

struct LandingView: View {
    let onSignIn: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                TopBar(onSignIn: onSignIn)
                VStack(alignment: .leading, spacing: 14) {
                    Text(title)
                        .textStyle(heroStyle)
                        .foregroundStyle(Theme.fg)
                        .accessibilityAddTraits(.isHeader)
                    Text("landing_lead").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgSoft)
                    Chain().padding(.top, 8)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 24)
                Rule(strong: false)
                ForEach(does.indices, id: \.self) { DoesRow(item: does[$0]) }
                Text("landing_accounts")
                    .textStyle(Theme.bodyMedium)
                    .foregroundStyle(Theme.fgMuted)
                    .padding(16)
            }
        }
        .background { Backdrop().ignoresSafeArea() }
        .background(Theme.canvas)
    }

    /// „Nimeni nu trebuie să observe primul.”, its end in red.
    private var title: AttributedString {
        var end = AttributedString(localized: "landing_title_end")
        end.foregroundColor = Theme.rosuFg
        return AttributedString(localized: "landing_title_start") + AttributedString(" ") + end
    }
}

private struct TopBar: View {
    let onSignIn: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            BrandMark(size: 26)
            Text("app_name")
                .textCase(.uppercase)
                .textStyle(brandStyle)
                .foregroundStyle(Theme.fg)
                .frame(maxWidth: .infinity, alignment: .leading)
            SnButton("landing_sign_in", kind: .link, action: onSignIn)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .overlay(alignment: .bottom) { Rule(strong: false) }
    }
}

/// The incident playing out step by step, then held on its code, then again.
private struct Chain: View {
    // Reduce Motion: the whole incident at once, standing still
    @Environment(\.accessibilityReduceMotion) private var still
    @State private var shown = 0
    @State private var trace: CGFloat = 0

    var body: some View {
        let shown = still ? steps.count + 1 : self.shown
        let trace = still ? 1 : self.trace
        VStack(spacing: 0) {
            HStack {
                Text("landing_example")
                    .textStyle(Theme.bodySmall)
                    .foregroundStyle(Theme.fgSoft)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Live(still: still)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            Rule(strong: false)
            ZStack(alignment: .topLeading) {
                Trace(progress: trace)
                HStack(alignment: .lastTextBaseline, spacing: 0) {
                    Text(verbatim: "128").textStyle(bpmStyle).foregroundStyle(Theme.fg)
                    Text("landing_bpm")
                        .textStyle(monoSmall)
                        .foregroundStyle(Theme.fgMuted)
                        .padding(.leading, 4)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .frame(height: 72)
            Rule(strong: false)
            VStack(alignment: .leading, spacing: 0) {
                ForEach(steps.indices, id: \.self) { i in
                    HStack(alignment: .top, spacing: 0) {
                        Text(verbatim: steps[i].at)
                            .textStyle(stepTimeStyle)
                            .foregroundStyle(Theme.fgMuted)
                            .frame(minWidth: 62, alignment: .leading)
                            .padding(.trailing, 4)
                        Text(LocalizedStringKey(steps[i].key))
                            .textStyle(Theme.bodyMedium)
                            .foregroundStyle(
                                quotes.contains(steps[i].key) ? Theme.fg : Theme.fgSoft)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 5)
                    .opacity(i < shown ? 1 : 0.14)
                    .animation(eased(0.5), value: shown)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 6)
            HStack(spacing: 8) {
                Rectangle().fill(Theme.rosu).frame(width: 9, height: 9)
                Text("landing_red").textStyle(redStyle).foregroundStyle(Theme.rosuFg)
                Text("landing_red_note").textStyle(Theme.bodySmall).foregroundStyle(redNote)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 11)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.rosu.opacity(0.12))
            .overlay(alignment: .top) { Rectangle().fill(Theme.rosu).frame(height: 2) }
            .opacity(shown > steps.count ? 1 : 0)
            .animation(eased(0.6), value: shown)
        }
        .background(Theme.inset.opacity(0.88))
        .overlay(Rectangle().strokeBorder(Theme.line, lineWidth: 1))
        .task(id: still) {
            guard !still else { return }
            while !Task.isCancelled {
                self.shown = 0
                var snap = Transaction()
                snap.disablesAnimations = true
                withTransaction(snap) { self.trace = 0 }
                guard (try? await Task.sleep(for: .milliseconds(400))) != nil else { return }
                withAnimation(eased(2.4)) { self.trace = 1 }
                for i in 0...steps.count {
                    guard (try? await Task.sleep(for: .milliseconds(stepMs))) != nil else { return }
                    self.shown = i + 1
                }
                guard (try? await Task.sleep(for: .milliseconds(holdMs))) != nil else { return }
            }
        }
    }
}

/// The blinking square and ÎN DESFĂȘURARE.
private struct Live: View {
    let still: Bool

    var body: some View {
        HStack(spacing: 6) {
            if still {
                Rectangle().fill(Theme.rosu).frame(width: 7, height: 7)
            } else {
                Rectangle().fill(Theme.rosu).frame(width: 7, height: 7)
                    .phaseAnimator([1.0, 0.2]) { square, alpha in
                        square.opacity(alpha)
                    } animation: { _ in
                        .linear(duration: 0.6)
                    }
            }
            Text("landing_live").textStyle(liveStyle).foregroundStyle(Theme.rosuFg)
        }
    }
}

// The pulse on a 480 × 92 grid, as on the web landing page: calm, then racing from x = 236.
private let calm: [(CGFloat, CGFloat)] = [
    (0, 60), (120, 60), (130, 52), (138, 64), (146, 60), (210, 60), (220, 54), (228, 63), (236, 60),
]
private let racing: [(CGFloat, CGFloat)] = [
    (236, 60), (262, 60), (270, 40), (278, 70), (290, 12), (302, 84), (312, 60), (332, 60),
    (340, 34), (348, 74), (358, 18), (368, 80), (378, 60), (404, 60), (412, 38), (420, 72),
    (430, 22), (440, 78), (450, 60), (480, 60),
]

private struct PulseLine: Shape {
    let points: [(CGFloat, CGFloat)]

    func path(in rect: CGRect) -> Path {
        Path { path in
            path.addLines(
                points.map { CGPoint(x: $0.0 / 480 * rect.width, y: $0.1 / 92 * rect.height) })
        }
    }
}

/// The calm line, and the racing one drawn up to `progress`.
private struct Trace: View {
    let progress: CGFloat

    var body: some View {
        ZStack {
            PulseLine(points: calm).stroke(Theme.lineStrong, lineWidth: 2)
            PulseLine(points: racing)
                .trim(from: 0, to: progress)
                .stroke(
                    Theme.rosu,
                    style: StrokeStyle(lineWidth: 2.4, lineCap: .round, lineJoin: .round))
        }
        .accessibilityHidden(true)
    }
}

private struct DoesRow: View {
    let item: Does

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: item.symbol)
                .font(.system(size: 18))
                .foregroundStyle(item.tint)
                .frame(width: 22, height: 22)
                .padding(.top, 2)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(LocalizedStringKey(item.title)).textStyle(doesTitleStyle).foregroundStyle(
                    Theme.fg)
                Text(LocalizedStringKey(item.text)).textStyle(Theme.bodyMedium).foregroundStyle(
                    Theme.fgMuted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .overlay(alignment: .bottom) { Rule(strong: false) }
    }
}

/// A faint grid fading out from the top right, under a red glow: the web page's backdrop.
private struct Backdrop: View {
    var body: some View {
        Canvas { context, size in
            let step: CGFloat = 32
            var grid = Path()
            var x: CGFloat = 0
            while x < size.width {
                grid.move(to: CGPoint(x: x, y: 0))
                grid.addLine(to: CGPoint(x: x, y: size.height))
                x += step
            }
            var y: CGFloat = 0
            while y < size.height {
                grid.move(to: CGPoint(x: 0, y: y))
                grid.addLine(to: CGPoint(x: size.width, y: y))
                y += step
            }
            context.stroke(grid, with: .color(Theme.line.opacity(0.32)), lineWidth: 1)
            let all = Path(CGRect(origin: .zero, size: size))
            context.fill(
                all,
                with: .radialGradient(
                    Gradient(colors: [.clear, Theme.canvas]),
                    center: CGPoint(x: size.width * 0.85, y: size.height * 0.08),
                    startRadius: 0, endRadius: size.width * 0.95))
            let glow = size.width * 0.85
            context.fill(
                Path(
                    ellipseIn: CGRect(
                        x: size.width - glow, y: -glow, width: glow * 2, height: glow * 2)),
                with: .radialGradient(
                    Gradient(colors: [Theme.rosu.opacity(0.16), .clear]),
                    center: CGPoint(x: size.width, y: 0),
                    startRadius: 0, endRadius: glow))
        }
        .accessibilityHidden(true)
    }
}
