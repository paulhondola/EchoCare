package ro.echocare.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * The DAS dashboard's palette (spec 07 §2.1, dashboard/src/styles.css): one dark theme, the same
 * hex values. The codes take their Romanian names from the status model (03).
 */
object Palette {
    val Canvas = Color(0xFF0D1117)
    val Subtle = Color(0xFF161B22)
    val Card = Color(0xFF21262D)
    val Inset = Color(0xFF010409)

    val Line = Color(0xFF30363D)
    val LineStrong = Color(0xFF6E7681)

    val Fg = Color(0xFFF0F6FC)
    val FgSoft = Color(0xFFC9D1D9)
    val FgMuted = Color(0xFF8B949E)
    val FgSubtle = Color(0xFF6E7681)
    val Off = Color(0xFF484F58)

    val Link = Color(0xFF58A6FF)

    val Rosu = Color(0xFFF85149)
    val RosuStrong = Color(0xFFDA3633)
    val RosuFg = Color(0xFFFF7B72)
    val Galben = Color(0xFFD29922)
    val GalbenFg = Color(0xFFE3B341)
    val Verde = Color(0xFF3FB950)
    val VerdeStrong = Color(0xFF238636)
    val VerdeFg = Color(0xFF56D364)
}
