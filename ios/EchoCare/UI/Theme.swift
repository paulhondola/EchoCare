import SwiftUI
import UIKit

/// The DAS dashboard's look (spec 07 §2), ported from android/app's ui/theme: one dark theme
/// (Palette.kt, the same hex values; the codes take their Romanian names from the status model, 03)
/// and the type scale (Type.kt). Modernist structure, as on Android: no rounded corners.
enum Theme {
    // Palette.kt
    static let canvas = Color(hex: 0x0D1117)
    static let subtle = Color(hex: 0x161B22)
    static let card = Color(hex: 0x21262D)
    static let inset = Color(hex: 0x010409)

    static let line = Color(hex: 0x30363D)
    static let lineStrong = Color(hex: 0x6E7681)

    static let fg = Color(hex: 0xF0F6FC)
    static let fgSoft = Color(hex: 0xC9D1D9)
    static let fgMuted = Color(hex: 0x8B949E)
    static let fgSubtle = Color(hex: 0x6E7681)
    static let off = Color(hex: 0x484F58)

    static let link = Color(hex: 0x58A6FF)

    static let rosu = Color(hex: 0xF85149)
    static let rosuStrong = Color(hex: 0xDA3633)
    static let rosuFg = Color(hex: 0xFF7B72)
    static let galben = Color(hex: 0xD29922)
    static let galbenFg = Color(hex: 0xE3B341)
    static let verde = Color(hex: 0x3FB950)
    static let verdeStrong = Color(hex: 0x238636)
    static let verdeFg = Color(hex: 0x56D364)

    // Type.kt: Archivo for the interface, JetBrains Mono for ids, times and phone numbers. Sizes
    // stay at phone reading size; headings and buttons ExtraBold, labels SemiBold.
    static let headlineLarge = TextStyle(size: 30, lineHeight: 34, face: .extraBold, tight: true)
    static let headlineMedium = TextStyle(size: 26, lineHeight: 30, face: .extraBold, tight: true)
    static let headlineSmall = TextStyle(size: 22, lineHeight: 26, face: .extraBold, tight: true)
    static let titleLarge = TextStyle(size: 20, lineHeight: 24, face: .extraBold, tight: true)
    static let titleMedium = TextStyle(size: 16, lineHeight: 22, face: .semiBold)
    static let titleSmall = TextStyle(size: 14, lineHeight: 20, face: .extraBold)
    static let bodyLarge = TextStyle(size: 16, lineHeight: 24, face: .regular)
    static let bodyMedium = TextStyle(size: 14, lineHeight: 20, face: .regular)
    static let bodySmall = TextStyle(size: 12, lineHeight: 16, face: .regular)
    static let labelLarge = TextStyle(size: 14, lineHeight: 18, face: .extraBold)
    static let labelMedium = TextStyle(size: 12, lineHeight: 16, face: .semiBold)
    static let labelSmall = TextStyle(size: 11, lineHeight: 14, face: .semiBold, trackingEm: 0.08)
    /// Phone numbers, ids and times
    static let mono = TextStyle(size: 14, lineHeight: nil, face: .monoMedium)
}

/// One step of the type scale. Compose's TextStyle has a line height and letter spacing in em;
/// SwiftUI puts them on the view, so `.textStyle(_:)` applies all three.
struct TextStyle: Sendable {
    /// The named instances of the bundled variable fonts (UI/Fonts, listed in UIAppFonts).
    enum Face: String, CaseIterable, Sendable {
        case regular = "ArchivoRoman-Regular"
        case semiBold = "Archivo-SemiBold"
        case bold = "ArchivoRoman-Bold"
        case extraBold = "ArchivoRoman-ExtraBold"
        case monoRegular = "JetBrainsMono-Regular"
        case monoMedium = "JetBrainsMonoRoman-Medium"
    }

    let size: CGFloat
    /// nil keeps the font's own line height, as Type.kt's Mono does.
    let lineHeight: CGFloat?
    let face: Face
    /// Letter spacing in em, as on Android: headings close up a little, as on the dashboard.
    let trackingEm: CGFloat

    init(
        size: CGFloat, lineHeight: CGFloat?, face: Face, tight: Bool = false,
        trackingEm: CGFloat? = nil
    ) {
        self.size = size
        self.lineHeight = lineHeight
        self.face = face
        self.trackingEm = trackingEm ?? (tight ? -0.015 : 0)
    }

    /// Scales with Dynamic Type, like sp on Android.
    var font: Font { .custom(face.rawValue, size: size) }

    var uiFont: UIFont { UIFont(name: face.rawValue, size: size) ?? .systemFont(ofSize: size) }
}

extension View {
    func textStyle(_ style: TextStyle) -> some View {
        font(style.font)
            .tracking(style.size * style.trackingEm)
            .lineSpacing(style.lineHeight.map { max(0, $0 - style.uiFont.lineHeight) } ?? 0)
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}
