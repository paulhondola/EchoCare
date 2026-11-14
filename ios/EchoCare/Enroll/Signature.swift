import Foundation

// The optional signature under the consent text (G7, UC-01 step 5, 04 §2): the strokes as drawn,
// as shares of the pad, thinned to what the server accepts. Pure, ported from
// android/app/.../enroll/Signature.kt; SignatureTests.swift ports SignatureTest.kt.

/// The consent text's version the server keeps with the strokes (SIGNATURE_CONSENT_TEXT).
let SIGNATURE_VERSION = "v1-semnatura"

/// The server refuses more points in all (04 §2).
let MAX_POINTS = 5000

struct Point: Equatable, Sendable {
    var x: Float
    var y: Float
}

/// Each coordinate as a share of the pad's `width` and `height`, clamped to 0...1.
func normalised(_ strokes: [[Point]], width: Float, height: Float) -> [[Point]] {
    strokes.map { stroke in
        stroke.map { Point(x: min(max($0.x / width, 0), 1), y: min(max($0.y / height, 0), 1)) }
    }
}

/// At most `max` points in all. Every stroke keeps its first and last point, so a tap stays one
/// point; the points between are spread evenly. A pad with more strokes than `max` has room for
/// keeps its first ones.
func thinned(_ strokes: [[Point]], max: Int = MAX_POINTS) -> [[Point]] {
    guard strokes.reduce(0, { $0 + $1.count }) > max else { return strokes }
    var ends = 0
    var fitting: [[Point]] = []
    for stroke in strokes {
        ends += min(stroke.count, 2)
        if ends > max { break }
        fitting.append(stroke)
    }
    let interior = fitting.reduce(0) { $0 + Swift.max($1.count - 2, 0) }
    let room = max - fitting.reduce(0) { $0 + min($1.count, 2) }
    return fitting.map { stroke in
        if stroke.count <= 2 { return stroke }
        let keep = (stroke.count - 2) * room / interior
        return evenly(stroke, count: keep + 2)
    }
}

/// `count` points of `stroke`, first and last among them, the rest evenly spaced.
private func evenly(_ stroke: [Point], count: Int) -> [Point] {
    (0..<count).map { stroke[$0 * (stroke.count - 1) / (count - 1)] }
}

/// The body of POST /seniors/{id}/signature: normalised, thinned, empty strokes dropped.
func signatureForm(_ strokes: [[Point]], width: Float, height: Float) -> SignatureForm {
    SignatureForm(
        textVersion: SIGNATURE_VERSION,
        strokes: thinned(normalised(strokes.filter { !$0.isEmpty }, width: width, height: height))
            .map { stroke in stroke.map { [$0.x, $0.y] } })
}

/// What a touch on the pad adds. `inProgress` is where the touch being drawn began (its
/// `startLocation` as shares), nil between touches; `touchStart` is where the touch just reported
/// began. A touch continues the last stroke only when it is the one in progress: SwiftUI never
/// calls `onEnded` for a gesture the scroll view or the system cancelled, and the next touch must
/// not be joined to the old stroke by a straight line that would be posted with the signature.
func drawn(
    _ strokes: [[Point]], inProgress: Point?, touchStart: Point, at point: Point
) -> (strokes: [[Point]], inProgress: Point?) {
    var strokes = strokes
    if inProgress == touchStart, !strokes.isEmpty {
        strokes[strokes.count - 1].append(point)
    } else {
        strokes.append([point])
    }
    return (strokes, touchStart)
}
