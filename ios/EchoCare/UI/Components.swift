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
    /// 48pt, 56pt for what a senior presses (Android's `BUTTON_HEIGHT`).
    var minHeight: CGFloat = 48
    let action: () -> Void

    init(
        _ text: LocalizedStringKey, kind: Kind = .neutral, fullWidth: Bool = false,
        systemImage: String? = nil, minHeight: CGFloat = 48, action: @escaping () -> Void
    ) {
        self.text = text
        self.kind = kind
        self.fullWidth = fullWidth
        self.systemImage = systemImage
        self.minHeight = minHeight
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
            .frame(minHeight: minHeight)
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

/// A full-width strip over a screen: no connection, a request sent (android Components.kt `Banner`).
/// VoiceOver reads it out when it appears, as Compose's polite live region.
struct Banner: View {
    /// A `Localizable.xcstrings` key.
    let key: String
    let tone: Tone

    init(_ key: String, tone: Tone) {
        self.key = key
        self.tone = tone
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Rectangle().fill(tone.dot).frame(width: 8, height: 8).accessibilityHidden(true)
                Text(LocalizedStringKey(key)).textStyle(Theme.labelLarge).foregroundStyle(tone.text)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(tone.fill)
            Rectangle().fill(tone.dot).frame(height: 2).accessibilityHidden(true)
        }
        .accessibilityElement(children: .combine)
        .onAppear { AccessibilityNotification.Announcement(String(localized: .init(key))).post() }
    }
}

/// One labelled row of a page: label column, value, an optional action, and its rule.
struct FieldRow<Value: View, Action: View>: View {
    let label: LocalizedStringKey
    var last = false
    let action: Action
    let value: Value

    init(
        _ label: LocalizedStringKey, last: Bool = false, @ViewBuilder action: () -> Action,
        @ViewBuilder value: () -> Value
    ) {
        self.label = label
        self.last = last
        self.action = action()
        self.value = value()
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                SectionLabel(label).frame(width: 112, alignment: .leading)
                // A value that does not fit beside the action wraps whole pieces, never letters
                WrappingRow(spacing: 8, lineSpacing: 4) { value }
                    .frame(maxWidth: .infinity, alignment: .leading)
                action
            }
            .padding(.vertical, 12)
            Rule(strong: last)
        }
    }
}

extension FieldRow where Action == EmptyView {
    init(_ label: LocalizedStringKey, last: Bool = false, @ViewBuilder value: () -> Value) {
        self.label = label
        self.last = last
        self.action = EmptyView()
        self.value = value()
    }
}

/// Lays its children out left to right, starting a new line where one does not fit (Compose's
/// `FlowRow`).
struct WrappingRow: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal.width ?? .infinity, subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let arranged = arrange(bounds.width, subviews)
        for (subview, origin) in zip(subviews, arranged.origins) {
            subview.place(at: CGPoint(x: bounds.minX + origin.x, y: bounds.minY + origin.y), proposal: .unspecified)
        }
    }

    private func arrange(_ width: CGFloat, _ subviews: Subviews) -> (size: CGSize, origins: [CGPoint]) {
        var origins: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var lineHeight: CGFloat = 0
        var widest: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + size.width > width {
                x = 0
                y += lineHeight + lineSpacing
                lineHeight = 0
            }
            origins.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            widest = max(widest, x - spacing)
            lineHeight = max(lineHeight, size.height)
        }
        return (CGSize(width: widest, height: y + lineHeight), origins)
    }
}

/// A phone number in mono with its FIX or MOBIL tag.
struct PhoneNumber: View {
    let e164: String
    let landline: Bool

    var body: some View {
        Text(verbatim: formatPhone(e164)).textStyle(Theme.mono).foregroundStyle(Theme.fg)
            .lineLimit(1).fixedSize()
        Text(landline ? "tag_landline" : "tag_mobile")
            .textCase(.uppercase)
            .textStyle(Theme.labelSmall)
            .foregroundStyle(Theme.fgMuted)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .overlay(Rectangle().strokeBorder(Theme.line, lineWidth: 1))
            .lineLimit(1).fixedSize()
    }
}

/// *Apelează*: opens the dialler with the number, the person presses call.
struct CallButton: View {
    let e164: String

    @Environment(\.openURL) private var openURL

    var body: some View {
        SnButton("call", kind: .link, systemImage: "phone.fill") {
            // The number stays on screen to dial by hand where there is no dialler
            if let url = URL(string: "tel:\(e164)") { openURL(url) }
        }
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
