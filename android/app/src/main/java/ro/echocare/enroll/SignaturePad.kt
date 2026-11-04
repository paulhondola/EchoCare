package ro.echocare.enroll

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.drag
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import java.time.ZoneId
import ro.echocare.R
import ro.echocare.home.shortDate
import ro.echocare.ui.Kind
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.theme.Palette

/**
 * The consent text and a pad to sign it on (G7, UC-01 step 5). Once [signedAt] is set, the date
 * stands in for the pad. The drawing stays until „Șterge", so a save that failed can be pressed
 * again; [onSave] gets the strokes and the pad's size in pixels.
 */
@Composable
fun ConsentSection(
    signedAt: String?,
    busy: Boolean,
    onSave: (List<List<Point>>, Float, Float) -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionLabel(stringResource(R.string.consent_label))
        Text(
            stringResource(R.string.consent_signature_note),
            color = Palette.FgMuted,
            style = MaterialTheme.typography.bodyMedium
        )
        Text(
            stringResource(R.string.consent_signature_text),
            style = MaterialTheme.typography.bodyLarge
        )
        if (signedAt != null) {
            Text(
                stringResource(
                    R.string.signed_on,
                    shortDate(signedAt, ZoneId.systemDefault(), true)
                ),
                color = Palette.VerdeFg,
                style = MaterialTheme.typography.titleMedium
            )
        } else {
            Pad(busy, onSave)
        }
    }
}

@Composable
private fun Pad(busy: Boolean, onSave: (List<List<Point>>, Float, Float) -> Unit) {
    var strokes by remember { mutableStateOf(emptyList<List<Point>>()) }
    var size by remember { mutableStateOf(Offset(1f, 1f)) }
    val dashed = PathEffect.dashPathEffect(floatArrayOf(16f, 10f))
    Box(
        Modifier
            .fillMaxWidth()
            .height(200.dp)
            .background(Palette.Inset)
            .onSizeChanged { size = Offset(it.width.toFloat(), it.height.toFloat()) }
            .pointerInput(Unit) {
                awaitEachGesture {
                    val down = awaitFirstDown()
                    // The first point is kept even when the finger never moves: a tap is a dot
                    var stroke = listOf(Point(down.position.x, down.position.y))
                    strokes = strokes + listOf(stroke)
                    down.consume()
                    drag(down.id) { change ->
                        stroke = stroke + Point(change.position.x, change.position.y)
                        strokes = strokes.dropLast(1) + listOf(stroke)
                        change.consume()
                    }
                }
            },
        contentAlignment = Alignment.Center
    ) {
        Canvas(Modifier.matchParentSize()) {
            drawRect(
                Palette.LineStrong,
                style = Stroke(width = 2.dp.toPx(), pathEffect = dashed)
            )
            strokes.forEach { stroke ->
                if (stroke.size == 1) {
                    drawCircle(Palette.Fg, 1.5.dp.toPx(), Offset(stroke[0].x, stroke[0].y))
                } else {
                    val path = Path().apply {
                        moveTo(stroke[0].x, stroke[0].y)
                        stroke.drop(1).forEach { lineTo(it.x, it.y) }
                    }
                    drawPath(
                        path,
                        Palette.Fg,
                        style = Stroke(3.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
                    )
                }
            }
        }
        if (strokes.isEmpty()) {
            Text(
                stringResource(R.string.sign_here),
                color = Palette.FgSubtle,
                style = MaterialTheme.typography.bodyLarge
            )
        }
    }
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        SnButton(
            stringResource(R.string.clear_signature),
            { strokes = emptyList() },
            kind = Kind.Outline,
            enabled = strokes.isNotEmpty() && !busy
        )
        SnButton(
            stringResource(R.string.save_signature),
            { onSave(strokes, size.x, size.y) },
            kind = Kind.Success,
            enabled = strokes.isNotEmpty() && !busy
        )
    }
}
