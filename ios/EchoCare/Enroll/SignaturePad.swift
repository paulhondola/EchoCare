import SwiftUI

/// The consent text and a pad to sign it on (G7, UC-01 step 5), ported from
/// android/app/.../enroll/SignaturePad.kt. Once `signedAt` is set, the date stands in for the pad.
/// The drawing stays until „Șterge”, a rotation included, so a save that failed can be pressed
/// again; `onSave` gets the body to post.
struct ConsentSection: View {
    let signedAt: String?
    let busy: Bool
    /// True while a stroke is being drawn: the enclosing ScrollView stops scrolling meanwhile.
    var drawing: Binding<Bool> = .constant(false)
    let onSave: (SignatureForm) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SectionLabel("consent_label")
            Text("consent_signature_note").textStyle(Theme.bodyMedium).foregroundStyle(
                Theme.fgMuted)
            Text("consent_signature_text").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fg)
            if let signedAt {
                Text(verbatim: localized("signed_on", shortDate(signedAt, year: true)))
                    .textStyle(Theme.titleMedium).foregroundStyle(Theme.verdeFg)
            } else {
                Pad(busy: busy, drawing: drawing, onSave: onSave)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// The pad with its two buttons. Strokes are kept as shares of the pad, so a rotation that resizes
/// it keeps the drawing; finger and Apple Pencil both arrive as the drag.
private struct Pad: View {
    let busy: Bool
    let drawing: Binding<Bool>
    let onSave: (SignatureForm) -> Void

    @State private var strokes: [[Point]] = []
    /// Where the stroke being drawn began; see `drawn`.
    @State private var inProgress: Point?
    /// True while a touch is down. A GestureState goes back to false when the touch ends or is
    /// cancelled, so a scroll view that takes the touch never leaves the page unscrollable.
    @GestureState private var touching = false
    @State private var size = CGSize(width: 1, height: 1)

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ZStack {
                Theme.inset
                Rectangle()
                    .strokeBorder(Theme.lineStrong, style: StrokeStyle(lineWidth: 2, dash: [8, 5]))
                Canvas { context, size in
                    for stroke in strokes {
                        let points = stroke.map {
                            CGPoint(x: CGFloat($0.x) * size.width, y: CGFloat($0.y) * size.height)
                        }
                        if points.count == 1 {
                            // A tap is a dot
                            let at = points[0]
                            context.fill(
                                Path(
                                    ellipseIn: CGRect(
                                        x: at.x - 1.5, y: at.y - 1.5, width: 3, height: 3)),
                                with: .color(Theme.fg))
                        } else if let first = points.first {
                            var path = Path()
                            path.move(to: first)
                            for point in points.dropFirst() { path.addLine(to: point) }
                            context.stroke(
                                path, with: .color(Theme.fg),
                                style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
                        }
                    }
                }
                if strokes.isEmpty {
                    Text("sign_here").textStyle(Theme.bodyLarge).foregroundStyle(Theme.fgSubtle)
                        .allowsHitTesting(false)
                }
            }
            .frame(height: 200)
            .onGeometryChange(for: CGSize.self, of: \.size) {
                size = CGSize(width: max($0.width, 1), height: max($0.height, 1))
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0, coordinateSpace: .local)
                    .updating($touching) { _, touching, _ in touching = true }
                    .onChanged { draw($0.location, from: $0.startLocation) }
                    .onEnded { _ in inProgress = nil }
            )
            .onChange(of: touching) { _, now in drawing.wrappedValue = now }
            .onDisappear { drawing.wrappedValue = false }
            .accessibilityElement()
            .accessibilityLabel(Text("sign_here"))
            .accessibilityAddTraits(.allowsDirectInteraction)

            WrappingRow(spacing: 8, lineSpacing: 8) {
                SnButton("clear_signature", kind: .outline) {
                    strokes = []
                    inProgress = nil
                }
                .disabled(strokes.isEmpty || busy)
                // Already shares: a pad of 1 by 1
                SnButton("save_signature", kind: .success) {
                    onSave(signatureForm(strokes, width: 1, height: 1))
                }
                .disabled(strokes.isEmpty || busy)
            }
        }
    }

    /// The first point is kept even when the finger never moves: a tap is a dot.
    private func draw(_ at: CGPoint, from start: CGPoint) {
        func share(_ p: CGPoint) -> Point {
            Point(x: Float(p.x / size.width), y: Float(p.y / size.height))
        }
        (strokes, inProgress) = drawn(
            strokes, inProgress: inProgress, touchStart: share(start), at: share(at))
    }
}
