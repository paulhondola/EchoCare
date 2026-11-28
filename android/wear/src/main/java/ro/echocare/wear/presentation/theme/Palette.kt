package ro.echocare.wear.presentation.theme

import androidx.compose.ui.graphics.Color

/**
 * The watch's colours, the same as the Apple Watch's `Palette.swift` (design 2026-11-14, watch
 * senior UI). The two button fills are dark enough for white text to read clearly.
 */
object Palette {
    /** „Nu mă simt bine” and „Nu, ajutor!”: the only red on the watch. */
    val Help = Color(0xFFC62A2F)

    /** „Da, sunt bine” and the ✓. */
    val Yes = Color(0xFF187A42)

    /** The home heart while monitoring runs. */
    val Calm = Color(0xFF3DD68C)

    /** The prompt's draining ring. */
    val Ring = Color(0xFFF5A524)
}
