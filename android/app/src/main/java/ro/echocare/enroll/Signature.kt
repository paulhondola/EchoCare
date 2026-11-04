package ro.echocare.enroll

import ro.echocare.SignatureForm

// The optional signature under the consent text (G7, UC-01 step 5, 04 §2): the strokes as drawn,
// as shares of the pad, thinned to what the server accepts. Pure, tested on the JVM.

/** The consent text's version the server keeps with the strokes (SIGNATURE_CONSENT_TEXT). */
const val SIGNATURE_VERSION = "v1-semnatura"

/** The server refuses more points in all (04 §2). */
const val MAX_POINTS = 5000

data class Point(val x: Float, val y: Float)

/** Each coordinate as a share of the pad's [width] and [height], clamped to 0..1. */
fun normalised(strokes: List<List<Point>>, width: Float, height: Float): List<List<Point>> =
    strokes.map { stroke ->
        stroke.map { Point((it.x / width).coerceIn(0f, 1f), (it.y / height).coerceIn(0f, 1f)) }
    }

/**
 * At most [max] points in all. Every stroke keeps its first and last point, so a tap stays one
 * point; the points between are spread evenly. A pad with more strokes than [max] has room for
 * keeps its first ones.
 */
fun thinned(strokes: List<List<Point>>, max: Int = MAX_POINTS): List<List<Point>> {
    if (strokes.sumOf { it.size } <= max) return strokes
    var ends = 0
    val fitting = strokes.takeWhile { stroke ->
        ends += minOf(stroke.size, 2)
        ends <= max
    }
    val interior = fitting.sumOf { maxOf(it.size - 2, 0) }
    val room = max - fitting.sumOf { minOf(it.size, 2) }
    return fitting.map { stroke ->
        if (stroke.size <= 2) {
            stroke
        } else {
            val keep = (stroke.size - 2).toLong() * room / interior
            evenly(stroke, keep.toInt() + 2)
        }
    }
}

/** [count] points of [stroke], first and last among them, the rest evenly spaced. */
private fun evenly(stroke: List<Point>, count: Int): List<Point> =
    List(count) { i -> stroke[(i.toLong() * (stroke.size - 1) / (count - 1)).toInt()] }

/** The body of POST /seniors/{id}/signature: normalised, thinned, empty strokes dropped. */
fun signatureForm(strokes: List<List<Point>>, width: Float, height: Float): SignatureForm =
    SignatureForm(
        SIGNATURE_VERSION,
        thinned(normalised(strokes.filter { it.isNotEmpty() }, width, height)).map { stroke ->
            stroke.map { listOf(it.x, it.y) }
        }
    )
