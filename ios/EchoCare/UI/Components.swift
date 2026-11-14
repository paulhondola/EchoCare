import SwiftUI

// The dashboard's pieces (spec 07, dashboard/src/styles.css), ported from android/app's
// ui/Components.kt: flush-left square buttons, tinted chips, uppercase field labels, 2pt section
// rules. Only what sign-in and the profile page use; Task 9 adds the rest of that file.

/// The colour of a chip, a card's bar or a banner. The codes take their Romanian names (03).
enum Tone {
    case verde, galben, rosu, link, muted

    var dot: Color {
        switch self {
        case .verde: Theme.verde
        case .galben: Theme.galben
        case .rosu: Theme.rosu
        case .link: Theme.link
        case .muted: Theme.fgMuted
        }
    }

    var text: Color {
        switch self {
        case .verde: Theme.verdeFg
        case .galben: Theme.galbenFg
        case .rosu: Theme.rosuFg
        case .link: Theme.link
        case .muted: Theme.fgSoft
        }
    }

    var fill: Color { self == .muted ? Theme.line : dot.opacity(0.15) }
}

/// A small tinted label with a square dot, like the dashboard's state chips.
struct Chip: View {
    let text: LocalizedStringKey
    let tone: Tone

    init(_ text: LocalizedStringKey, tone: Tone) {
        self.text = text
        self.tone = tone
    }

    var body: some View {
        HStack(spacing: 6) {
            Rectangle().fill(tone.dot).frame(width: 6, height: 6)
            Text(text).textStyle(Theme.labelMedium).foregroundStyle(tone.text)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(tone.fill)
    }
}

/// The dashboard's sn-btn variants.
enum Kind {
    case neutral, danger, success, link, outline

    fileprivate var colors: (fill: Color, border: Color, content: Color) {
        switch self {
        case .neutral: (Theme.card, Theme.line, Theme.fg)
        case .danger: (Theme.rosuStrong, Theme.rosu, .white)
        case .success: (Theme.verdeStrong, Theme.verde, .white)
        case .link: (Theme.card, Theme.line, Theme.link)
        case .outline: (.clear, Theme.lineStrong, Theme.fg)
        }
    }
}

/// A square button whose label starts at the left padding, however wide it is. `fullWidth` plays
/// the part of Compose's `Modifier.fillMaxWidth()`, which SwiftUI can't apply from outside.
struct SnButton: View {
    let text: LocalizedStringKey
    var kind: Kind = .neutral
    var fullWidth = false
    var systemImage: String?
    let action: () -> Void

    init(
        _ text: LocalizedStringKey, kind: Kind = .neutral, fullWidth: Bool = false,
        systemImage: String? = nil, action: @escaping () -> Void
    ) {
        self.text = text
        self.kind = kind
        self.fullWidth = fullWidth
        self.systemImage = systemImage
        self.action = action
    }

    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        let colors = kind.colors
        Button(action: action) {
            HStack(spacing: 8) {
                if let systemImage {
                    Image(systemName: systemImage).font(.system(size: 14)).accessibilityHidden(true)
                }
                Text(text).textStyle(Theme.labelLarge)
            }
            .foregroundStyle(colors.content)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(minHeight: 48)
            .frame(maxWidth: fullWidth ? .infinity : nil, alignment: .leading)
            .background(colors.fill)
            .overlay(Rectangle().strokeBorder(colors.border, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.45)
    }
}

/// A bordered square icon button: back, close.
struct SquareIconButton: View {
    let systemImage: String
    let description: LocalizedStringKey
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.fgSoft)
                .frame(width: 48, height: 48)
                .overlay(Rectangle().strokeBorder(Theme.line, lineWidth: 1))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text(description))
    }
}

/// Small uppercase label over or beside a value.
struct SectionLabel: View {
    let text: LocalizedStringKey

    init(_ text: LocalizedStringKey) { self.text = text }

    var body: some View {
        Text(text)
            .textCase(.uppercase)
            .textStyle(Theme.labelSmall)
            .foregroundStyle(Theme.fgMuted)
    }
}

/// A rule between rows (1pt) or under a section (2pt).
struct Rule: View {
    var strong = true

    var body: some View {
        Rectangle().fill(Theme.line).frame(height: strong ? 2 : 1).accessibilityHidden(true)
    }
}

/// Red text under a form that VoiceOver reads out when it appears, as Compose's polite live region.
struct ErrorText: View {
    let key: String

    var body: some View {
        Text(LocalizedStringKey(key))
            .textStyle(Theme.bodyMedium)
            .foregroundStyle(Theme.rosuFg)
            .frame(maxWidth: .infinity, alignment: .leading)
            .onAppear { AccessibilityNotification.Announcement(String(localized: .init(key))).post() }
    }
}

/// The dashboard's inset field: square, dark, blue border while typing. `mono` for numbers and
/// codes; names and places in Archivo.
struct SnTextField: View {
    @Binding var text: String
    let label: LocalizedStringKey
    var keyboard: UIKeyboardType = .default
    var content: UITextContentType?
    var mono = true

    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionLabel(label)
            TextField("", text: $text)
                .keyboardType(keyboard)
                .textContentType(content)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .focused($focused)
                .font(.custom((mono ? TextStyle.Face.monoMedium : .regular).rawValue, size: 16))
                .foregroundStyle(Theme.fg)
                .tint(Theme.link)
                .padding(.horizontal, 14)
                .frame(minHeight: 52)
                .background(Theme.inset)
                .overlay(
                    Rectangle().strokeBorder(focused ? Theme.link : Theme.line, lineWidth: focused ? 2 : 1)
                )
                .accessibilityLabel(Text(label))
        }
    }
}

/// The app's mark (android res/drawable/ic_brand.xml): a dark rounded square, a sound wave in white
/// and a pulse in red, drawn on its 100 × 100 grid.
struct BrandMark: View {
    var size: CGFloat

    var body: some View {
        Canvas { context, canvasSize in
            let s = canvasSize.width / 100
            func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: x * s, y: y * s) }
            let red = Color(hex: 0xEF4444)
            context.fill(
                Path(roundedRect: CGRect(origin: .zero, size: canvasSize), cornerRadius: 22 * s),
                with: .color(Color(hex: 0x1B1B1B)))
            var wave = Path()
            for (x, y0, y1) in [
                (12.0, 45.0, 55.0), (18, 32, 68), (24, 41, 59), (30, 22, 78), (36, 38, 62), (42, 28, 72),
                (48, 43, 57),
            ] {
                wave.move(to: p(x, y0))
                wave.addLine(to: p(x, y1))
            }
            context.stroke(wave, with: .color(.white), style: StrokeStyle(lineWidth: 3.2 * s, lineCap: .round))
            var pulse = Path()
            pulse.addLines([
                p(54, 50), p(59, 50), p(62, 43), p(65, 53), p(70, 28), p(76, 72), p(81, 50), p(88, 50),
            ])
            context.stroke(
                pulse, with: .color(red), style: StrokeStyle(lineWidth: 3.2 * s, lineCap: .round, lineJoin: .round))
            context.fill(
                Path(ellipseIn: CGRect(x: (89 - 3.8) * s, y: (50 - 3.8) * s, width: 7.6 * s, height: 7.6 * s)),
                with: .color(red))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
