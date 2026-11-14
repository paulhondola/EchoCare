import Foundation
import Testing

@testable import EchoCare

// G7, UC-01 step 5, 04 §2: the signature's strokes as the server takes them. Ported from android's
// SignatureTest.kt.
struct SignatureTests {
    @Test func `points are shares of the pad`() {
        #expect(
            normalised([[Point(x: 50, y: 25)]], width: 100, height: 50) == [[Point(x: 0.5, y: 0.5)]])
    }

    @Test func `points outside the pad are clamped`() {
        #expect(
            normalised([[Point(x: -3, y: 70)]], width: 100, height: 50) == [[Point(x: 0, y: 1)]])
    }

    @Test func `a tap is one point`() {
        let form = signatureForm([[Point(x: 10, y: 10)]], width: 100, height: 100)
        #expect(form.strokes == [[[0.1, 0.1]]])
    }

    @Test func `a long signature is thinned to at most 5000 and keeps each stroke's ends`() {
        let strokes = (0..<3).map { s in (0..<4000).map { Point(x: Float($0), y: Float(s)) } }
        let thin = thinned(strokes)
        #expect(thin.map(\.count).reduce(0, +) <= MAX_POINTS)
        for (before, after) in zip(strokes, thin) {
            #expect(before.first == after.first)
            #expect(before.last == after.last)
            #expect(after.count >= 2)
        }
    }

    @Test func `a short signature is untouched`() {
        let strokes = [[Point(x: 1, y: 1), Point(x: 2, y: 2)], [Point(x: 3, y: 3)]]
        #expect(thinned(strokes) == strokes)
    }

    @Test func `the form carries v1-semnatura and drops an empty stroke`() {
        let form = signatureForm([[], [Point(x: 0, y: 0)]], width: 10, height: 10)
        #expect(form.textVersion == "v1-semnatura")
        #expect(form.strokes.count == 1)
    }

    // What the server reads: text_version and strokes as lists of [x, y] shares
    @Test func `the body is text_version and strokes of x y pairs`() throws {
        let form = signatureForm([[Point(x: 5, y: 10), Point(x: 10, y: 5)]], width: 10, height: 10)
        let json = try JSONSerialization.jsonObject(
            with: ApiClient.makeEncoder().encode(form)) as? [String: Any]
        #expect(json?["text_version"] as? String == "v1-semnatura")
        #expect(json?["strokes"] as? [[[Double]]] == [[[0.5, 1.0], [1.0, 0.5]]])
    }

    // More strokes than the limit has room for: the first ones stay (Signature.kt `thinned`)
    @Test func `a pad with more strokes than points keeps its first ones`() {
        let strokes = (0..<6).map { _ in [Point(x: 0, y: 0), Point(x: 1, y: 1)] }
        let thin = thinned(strokes, max: 7)
        #expect(thin.count == 3)
        #expect(thin.map(\.count).reduce(0, +) <= 7)
    }
}
