package bia.sentinela.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import bia.sentinela.R

// The dashboard's type (spec 07 §2): Archivo for the interface, JetBrains Mono for ids, times
// and phone numbers. Both are variable fonts in res/font, licences in assets/licenses.

// Picking a weight out of a variable font is still marked experimental in Compose
@OptIn(ExperimentalTextApi::class)
private fun archivo(weight: Int) = Font(
    R.font.archivo,
    weight = FontWeight(weight),
    variationSettings = FontVariation.Settings(FontVariation.weight(weight))
)

@OptIn(ExperimentalTextApi::class)
private fun mono(weight: Int) = Font(
    R.font.jetbrains_mono,
    weight = FontWeight(weight),
    variationSettings = FontVariation.Settings(FontVariation.weight(weight))
)

val Archivo = FontFamily(archivo(400), archivo(600), archivo(700), archivo(800))
val JetBrainsMono = FontFamily(mono(400), mono(500), mono(600))

private fun style(size: Int, line: Int, weight: FontWeight, tight: Boolean = false) = TextStyle(
    fontFamily = Archivo,
    fontWeight = weight,
    fontSize = size.sp,
    lineHeight = line.sp,
    // Headings close up a little, as on the dashboard
    letterSpacing = if (tight) (-0.015).em else 0.em
)

// Sizes stay at phone reading size; weights and spacing follow the dashboard: headings
// ExtraBold, buttons ExtraBold, labels SemiBold.
val Typography = Typography(
    headlineLarge = style(30, 34, FontWeight.ExtraBold, tight = true),
    headlineMedium = style(26, 30, FontWeight.ExtraBold, tight = true),
    headlineSmall = style(22, 26, FontWeight.ExtraBold, tight = true),
    titleLarge = style(20, 24, FontWeight.ExtraBold, tight = true),
    titleMedium = style(16, 22, FontWeight.SemiBold),
    titleSmall = style(14, 20, FontWeight.ExtraBold),
    bodyLarge = style(16, 24, FontWeight.Normal),
    bodyMedium = style(14, 20, FontWeight.Normal),
    bodySmall = style(12, 16, FontWeight.Normal),
    labelLarge = style(14, 18, FontWeight.ExtraBold),
    labelMedium = style(12, 16, FontWeight.SemiBold),
    labelSmall = style(11, 14, FontWeight.SemiBold).copy(letterSpacing = 0.08.em)
)

/** Phone numbers, ids and times */
val Mono = TextStyle(fontFamily = JetBrainsMono, fontWeight = FontWeight.Medium, fontSize = 14.sp)
