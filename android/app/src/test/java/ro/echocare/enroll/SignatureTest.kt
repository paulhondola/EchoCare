package ro.echocare.enroll

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SignatureTest {
    @Test
    fun `points are shares of the pad`() {
        assertEquals(
            listOf(listOf(Point(0.5f, 0.5f))),
            normalised(listOf(listOf(Point(50f, 25f))), 100f, 50f)
        )
    }

    @Test
    fun `points outside the pad are clamped`() {
        assertEquals(
            listOf(listOf(Point(0f, 1f))),
            normalised(listOf(listOf(Point(-3f, 70f))), 100f, 50f)
        )
    }

    @Test
    fun `a tap is one point`() {
        val form = signatureForm(listOf(listOf(Point(10f, 10f))), 100f, 100f)
        assertEquals(listOf(listOf(listOf(0.1f, 0.1f))), form.strokes)
    }

    @Test
    fun `a long signature is thinned to at most 5000 and keeps each stroke's ends`() {
        val strokes = List(3) { s -> List(4000) { Point(it.toFloat(), s.toFloat()) } }
        val thin = thinned(strokes)
        assertTrue(thin.sumOf { it.size } <= MAX_POINTS)
        strokes.zip(thin).forEach { (before, after) ->
            assertEquals(before.first(), after.first())
            assertEquals(before.last(), after.last())
            assertTrue(after.size >= 2)
        }
    }

    @Test
    fun `a short signature is untouched`() {
        val strokes = listOf(listOf(Point(1f, 1f), Point(2f, 2f)), listOf(Point(3f, 3f)))
        assertEquals(strokes, thinned(strokes))
    }

    @Test
    fun `the form carries v1-semnatura and drops an empty stroke`() {
        val form = signatureForm(listOf(emptyList(), listOf(Point(0f, 0f))), 10f, 10f)
        assertEquals("v1-semnatura", form.textVersion)
        assertEquals(1, form.strokes.size)
    }
}
