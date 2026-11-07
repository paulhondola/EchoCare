package ro.echocare.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// The dashboard's one dark theme (spec 07 §2.1) as a Material 3 scheme, so the Material pieces
// still in use (text fields, menus, spinners) match. Never the wallpaper's dynamic colours.
private val EchoCareColors = darkColorScheme(
    primary = Palette.Link,
    onPrimary = Palette.Canvas,
    primaryContainer = Palette.Card,
    onPrimaryContainer = Palette.Fg,
    secondary = Palette.FgSoft,
    onSecondary = Palette.Canvas,
    secondaryContainer = Palette.Card,
    onSecondaryContainer = Palette.Fg,
    tertiary = Palette.Verde,
    onTertiary = Palette.Canvas,
    background = Palette.Canvas,
    onBackground = Palette.Fg,
    surface = Palette.Canvas,
    onSurface = Palette.Fg,
    surfaceVariant = Palette.Card,
    onSurfaceVariant = Palette.FgMuted,
    surfaceContainerLowest = Palette.Inset,
    surfaceContainerLow = Palette.Subtle,
    surfaceContainer = Palette.Subtle,
    surfaceContainerHigh = Palette.Card,
    surfaceContainerHighest = Palette.Card,
    outline = Palette.Line,
    outlineVariant = Palette.Card,
    error = Palette.Rosu,
    onError = Color.White,
    errorContainer = Palette.RosuStrong,
    onErrorContainer = Color.White,
    scrim = Palette.Inset
)

// Modernist structure: no rounded corner anywhere
private val Square = RoundedCornerShape(0.dp)

private val EchoCareShapes = Shapes(
    extraSmall = Square,
    small = Square,
    medium = Square,
    large = Square,
    extraLarge = Square
)

@Composable
fun EchoCareTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = EchoCareColors,
        typography = Typography,
        shapes = EchoCareShapes,
        content = content
    )
}
