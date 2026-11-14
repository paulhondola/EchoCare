import Foundation

// Ported from android/app/.../ui/Format.kt: the helpers the top bar and the profile page need.
// Task 9 adds the rest of that file.

/// A Romanian number grouped as people read it; any other number as it is.
func formatPhone(_ e164: String) -> String {
    guard let match = e164.wholeMatch(of: /\+40(\d{9})/) else { return e164 }
    let n = Array("0" + match.1)
    func part(_ from: Int, _ to: Int) -> String { String(n[from..<to]) }
    // Bucharest landlines have a three-digit prefix (021, 031); the rest four (0722, 0264)
    if n[1] == "2" || n[1] == "3", n[2] == "1" {
        return "\(part(0, 3)) \(part(3, 6)) \(part(6, n.count))"
    }
    return "\(part(0, 4)) \(part(4, 7)) \(part(7, n.count))"
}

/// The letters for a person's square in the top bar (UC-12, 04 §1 `/profile`): the first letters of
/// the first and last word, capitalised, titles such as "Dr." left out. One word gives one letter.
func initials(_ name: String) -> String {
    let words = name.split(whereSeparator: \.isWhitespace).filter { !$0.hasSuffix(".") }
    guard let first = words.first else { return "" }
    let picked = words.count > 1 ? [first, words[words.count - 1]] : [first]
    return picked.map { $0.prefix(1).uppercased() }.joined()
}
