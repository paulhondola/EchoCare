package bia.sentinela.shared

import org.junit.Assert.assertEquals
import org.junit.Test

private val ARM_SWING = listOf(0.6f, 1.6f)

// Synthetic traces at the watch's 50 readings a second, shaped after the S13 trials (spike-results.md)
class FallDetectorTest {
    private val periodMs = 20L

    private class Trace {
        val readings = mutableListOf<Float>()

        fun hold(g: Float, ms: Long) = repeat((ms / 20).toInt()) { readings += g }

        fun impact(g: Float) {
            readings += g
        }

        // Arm movement, alternating around 1 g by more than the stillness tolerance
        fun move(ms: Long) = repeat((ms / 20).toInt()) { readings += ARM_SWING[it % 2] }
    }

    private fun detections(build: Trace.() -> Unit): Int {
        val detector = FallDetector()
        val trace = Trace().apply(build)
        return trace.readings.withIndex().count { (i, g) -> detector.onReading(i * periodMs, g) }
    }

    @Test
    fun `a fall with a strong impact, then stillness, is detected once`() {
        assertEquals(
            1,
            detections {
                hold(1f, 1_000)
                impact(8.3f)
                move(1_500)
                hold(1f, 15_000)
            }
        )
    }

    @Test
    fun `a soft fall backwards onto a bed is detected`() {
        assertEquals(
            1,
            detections {
                hold(1f, 1_000)
                impact(2.04f)
                move(1_000)
                hold(1.02f, 10_000)
            }
        )
    }

    @Test
    fun `a slap on a table, with the arm moving on, is not a fall`() {
        assertEquals(
            0,
            detections {
                hold(1f, 1_000)
                impact(11.8f)
                move(15_000)
            }
        )
    }

    @Test
    fun `walking with a peak below the impact threshold is not a fall`() {
        assertEquals(
            0,
            detections {
                repeat(10) {
                    impact(1.9f)
                    move(500)
                }
                hold(1f, 10_000)
            }
        )
    }

    @Test
    fun `stillness shorter than seven seconds is not a fall`() {
        assertEquals(
            0,
            detections {
                impact(5f)
                hold(1f, 6_000)
                move(5_000)
            }
        )
    }

    @Test
    fun `stillness that begins long after the impact is not a fall`() {
        assertEquals(
            0,
            detections {
                impact(5f)
                move(6_000)
                hold(1f, 10_000)
            }
        )
    }

    @Test
    fun `sitting down hard matches, and the wrist prompt is what catches it`() {
        assertEquals(
            1,
            detections {
                impact(2.74f)
                hold(1f, 10_000)
            }
        )
    }

    @Test
    fun `acceleration at rest is one g`() {
        assertEquals(1f, FallDetector.accelerationG(0f, 0f, 9.80665f), 0.001f)
    }
}
