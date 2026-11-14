import SwiftUI
import Testing
import UIKit

@testable import EchoCare

// FieldRow's value wraps whole pieces onto new lines, and a piece wider than the line wraps its text.
@MainActor
struct WrappingRowTests {
    private func height(of view: some View, width: CGFloat) -> CGFloat {
        UIHostingController(rootView: view)
            .sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude)).height
    }

    @Test func aLongTextWrapsInsteadOfOverflowing() {
        let long = String(repeating: "Strada Mihai Eminescu numărul 12 ", count: 4)
        let wide = height(of: WrappingRow { Text(verbatim: long) }, width: 600)
        let narrow = height(of: WrappingRow { Text(verbatim: long) }, width: 200)
        #expect(narrow > wide * 2)
    }

    @Test func shortPiecesSitSideBySideAndWrapWhenFull() {
        func row(_ width: CGFloat) -> CGFloat {
            height(
                of: WrappingRow {
                    Color.red.frame(width: 80, height: 20); Color.blue.frame(width: 80, height: 20)
                }, width: width)
        }
        #expect(row(200) == 20)
        #expect(row(120) > 20)
    }
}
