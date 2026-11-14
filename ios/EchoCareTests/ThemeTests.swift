import Testing
import UIKit

@testable import EchoCare

// A missing font falls back to the system font without a word, so check every face loads.
struct ThemeTests {
    @Test("Every face of the type scale is a bundled font", arguments: TextStyle.Face.allCases)
    func faceIsBundled(_ face: TextStyle.Face) {
        #expect(UIFont(name: face.rawValue, size: 12) != nil)
    }
}
