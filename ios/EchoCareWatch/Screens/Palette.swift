import SwiftUI

/// The watch's colours (design 2026-11-14, watch senior UI). The two button fills are dark enough
/// for white 17 pt text to read clearly.
enum Palette {
    /// „Nu mă simt bine” and „Nu, ajutor!”: the only red on the watch.
    static let help = Color(red: 0xC6 / 255, green: 0x2A / 255, blue: 0x2F / 255)
    /// „Da, sunt bine” and the ✓.
    static let yes = Color(red: 0x18 / 255, green: 0x7A / 255, blue: 0x42 / 255)
    /// The home heart while monitoring runs.
    static let calm = Color(red: 0x3D / 255, green: 0xD6 / 255, blue: 0x8C / 255)
    /// The prompt's draining ring.
    static let ring = Color(red: 0xF5 / 255, green: 0xA5 / 255, blue: 0x24 / 255)
}
