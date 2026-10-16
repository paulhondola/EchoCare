package ro.echocare.ui

import android.content.ActivityNotFoundException
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.net.toUri
import ro.echocare.R
import ro.echocare.ui.theme.Mono
import ro.echocare.ui.theme.Palette

// The dashboard's pieces (spec 07, dashboard/src/styles.css) in Compose: flush-left square
// buttons, tinted chips, uppercase field labels, 2dp section rules.

/** The colour of a chip, a card's bar or a banner. The codes take their Romanian names (03). */
enum class Tone(val dot: Color, val text: Color, val fill: Color) {
    Verde(Palette.Verde, Palette.VerdeFg, Palette.Verde.copy(alpha = 0.15f)),
    Galben(Palette.Galben, Palette.GalbenFg, Palette.Galben.copy(alpha = 0.15f)),
    Rosu(Palette.Rosu, Palette.RosuFg, Palette.Rosu.copy(alpha = 0.15f)),
    Link(Palette.Link, Palette.Link, Palette.Link.copy(alpha = 0.15f)),
    Muted(Palette.FgMuted, Palette.FgSoft, Palette.Line)
}

/** A small tinted label with a square dot, like the dashboard's state chips. */
@Composable
fun Chip(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Row(
        modifier
            .background(tone.fill)
            .padding(horizontal = 8.dp, vertical = 3.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(6.dp).background(tone.dot))
        Text(text, color = tone.text, style = MaterialTheme.typography.labelMedium)
    }
}

/** The dashboard's sn-btn variants. */
enum class Kind { Neutral, Danger, Success, Link, Outline }

/** A square button whose label starts at the left padding, however wide it is. */
@Composable
fun SnButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    kind: Kind = Kind.Neutral,
    enabled: Boolean = true,
    icon: Painter? = null
) {
    val (fill, border, content) = when (kind) {
        Kind.Neutral -> Triple(Palette.Card, Palette.Line, Palette.Fg)
        Kind.Danger -> Triple(Palette.RosuStrong, Palette.Rosu, Color.White)
        Kind.Success -> Triple(Palette.VerdeStrong, Palette.Verde, Color.White)
        Kind.Link -> Triple(Palette.Card, Palette.Line, Palette.Link)
        Kind.Outline -> Triple(Color.Transparent, Palette.LineStrong, Palette.Fg)
    }
    Row(
        modifier
            .alpha(if (enabled) 1f else 0.45f)
            .heightIn(min = 44.dp)
            .background(fill)
            .border(1.dp, border)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        icon?.let { Icon(it, null, Modifier.size(16.dp), tint = content) }
        Text(text, color = content, style = MaterialTheme.typography.labelLarge)
    }
}

/** A bordered square icon button: back, menu, close. */
@Composable
fun SquareIconButton(painter: Painter, description: String, onClick: () -> Unit) {
    Box(
        Modifier
            .size(44.dp)
            .border(1.dp, Palette.Line)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Icon(painter, description, Modifier.size(18.dp), tint = Palette.FgSoft)
    }
}

/** Small uppercase label over or beside a value. */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text.uppercase(),
        modifier,
        color = Palette.FgMuted,
        style = MaterialTheme.typography.labelSmall
    )
}

/** A rule between rows (1dp) or under a section (2dp). */
@Composable
fun Rule(modifier: Modifier = Modifier, strong: Boolean = true) {
    HorizontalDivider(modifier, thickness = if (strong) 2.dp else 1.dp, color = Palette.Line)
}

/** One labelled row of a page: label column, value, an optional action, and its rule. */
@Composable
fun FieldRow(
    label: String,
    last: Boolean = false,
    action: (@Composable () -> Unit)? = null,
    value: @Composable () -> Unit
) {
    Column {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            SectionLabel(label, Modifier.width(112.dp))
            // A value that does not fit beside the action wraps whole pieces, never letters
            FlowRow(
                Modifier.weight(1f),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) { value() }
            action?.invoke()
        }
        Rule(strong = last)
    }
}

/** A full-width strip over a screen: no connection, nobody on duty. */
@Composable
fun Banner(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth()) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(tone.fill)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(8.dp).background(tone.dot))
            Text(text, color = tone.text, style = MaterialTheme.typography.labelLarge)
        }
        HorizontalDivider(thickness = 2.dp, color = tone.dot)
    }
}

/** A phone number in mono with its FIX or MOBIL tag. */
@Composable
fun PhoneNumber(e164: String, landline: Boolean) {
    Text(formatPhone(e164), style = Mono, color = Palette.Fg, maxLines = 1, softWrap = false)
    Text(
        stringResource(if (landline) R.string.tag_landline else R.string.tag_mobile).uppercase(),
        Modifier
            .border(1.dp, Palette.Line)
            .padding(horizontal = 5.dp, vertical = 1.dp),
        color = Palette.FgMuted,
        maxLines = 1,
        softWrap = false,
        style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp)
    )
}

/** *Apelează*: opens the dialler with the number, the person presses call (no permission). */
@Composable
fun CallButton(e164: String) {
    val context = LocalContext.current
    SnButton(
        stringResource(R.string.call),
        onClick = {
            try {
                context.startActivity(Intent(Intent.ACTION_DIAL, "tel:$e164".toUri()))
            } catch (e: ActivityNotFoundException) {
                // A tablet without a dialler: the number stays on screen to dial by hand
            }
        },
        kind = Kind.Link,
        icon = painterResource(R.drawable.ic_phone)
    )
}

/**
 * The dashboard's inset field: square, dark, blue border while typing, red with [error] under it.
 * [mono] for numbers and codes; names and places in Archivo.
 */
@Composable
fun SnTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    keyboardType: KeyboardType,
    modifier: Modifier = Modifier,
    mono: Boolean = true,
    hint: String? = null,
    error: String? = null,
    capitalization: KeyboardCapitalization = KeyboardCapitalization.None
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        SectionLabel(label)
        OutlinedTextField(
            value,
            onValueChange,
            Modifier
                .fillMaxWidth()
                .semantics { contentDescription = label },
            textStyle = (if (mono) Mono else MaterialTheme.typography.bodyLarge)
                .copy(fontSize = 16.sp, color = Palette.Fg),
            placeholder = hint?.let { { Text(it, color = Palette.FgSubtle) } },
            isError = error != null,
            keyboardOptions = KeyboardOptions(
                capitalization = capitalization,
                keyboardType = keyboardType
            ),
            singleLine = true,
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = Palette.Inset,
                unfocusedContainerColor = Palette.Inset,
                errorContainerColor = Palette.Inset,
                focusedBorderColor = Palette.Link,
                unfocusedBorderColor = Palette.Line,
                errorBorderColor = Palette.Rosu,
                cursorColor = Palette.Link,
                errorCursorColor = Palette.Rosu
            )
        )
        error?.let {
            Text(it, color = Palette.RosuFg, style = MaterialTheme.typography.bodyMedium)
        }
    }
}
