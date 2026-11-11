package ro.echocare.auth

import android.provider.Settings
import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import ro.echocare.R
import ro.echocare.ui.Kind
import ro.echocare.ui.SnButton
import ro.echocare.ui.theme.Mono
import ro.echocare.ui.theme.Palette

// The signed-out first screen: the system that watches and reacts on its own (UC-09, UC-07,
// UC-11), the dashboard's landing page folded to a phone. *Intrați* leads on to the phone step.

private val EaseOut = CubicBezierEasing(0.16f, 1f, 0.3f, 1f)
private const val STEP_MS = 900L
private const val HOLD_MS = 4200L

/** One illustrative incident, as the web landing page plays it. */
private val STEPS = listOf(
    "14:20:03" to R.string.landing_step_1,
    "14:20:04" to R.string.landing_step_2,
    "14:20:36" to R.string.landing_step_3,
    "14:20:58" to R.string.landing_step_4,
    "14:20:58" to R.string.landing_step_5,
    "14:21:01" to R.string.landing_step_6
)

/** The senior's own words, set brighter than the system's lines. */
private val QUOTES = setOf(R.string.landing_step_4)

private class Does(
    @DrawableRes val icon: Int,
    val tint: Color,
    @StringRes val title: Int,
    @StringRes val text: Int
)

private val DOES = listOf(
    Does(
        R.drawable.ic_watch,
        Palette.Link,
        R.string.landing_observe,
        R.string.landing_observe_text
    ),
    Does(R.drawable.ic_phone, Palette.Fg, R.string.landing_call, R.string.landing_call_text),
    Does(
        R.drawable.ic_scale,
        Palette.RosuFg,
        R.string.landing_decide,
        R.string.landing_decide_text
    ),
    Does(
        R.drawable.ic_headset,
        Palette.VerdeFg,
        R.string.landing_hand_over,
        R.string.landing_hand_over_text
    )
)

@Composable
fun Landing(onSignIn: () -> Unit, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize().drawBehind { backdrop() }) {
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
            TopBar(onSignIn)
            Column(
                Modifier.padding(horizontal = 16.dp, vertical = 24.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                Text(
                    buildAnnotatedString {
                        append(stringResource(R.string.landing_title_start))
                        append(" ")
                        withStyle(SpanStyle(color = Palette.RosuFg)) {
                            append(stringResource(R.string.landing_title_end))
                        }
                    },
                    Modifier.semantics { heading() },
                    color = Palette.Fg,
                    style = MaterialTheme.typography.headlineLarge.copy(
                        fontSize = 36.sp,
                        lineHeight = 36.sp,
                        letterSpacing = (-0.035).em
                    )
                )
                Text(
                    stringResource(R.string.landing_lead),
                    color = Palette.FgSoft,
                    style = MaterialTheme.typography.bodyLarge
                )
                Chain(Modifier.padding(top = 8.dp))
            }
            HorizontalDivider(thickness = 1.dp, color = Palette.Line)
            DOES.forEach { DoesRow(it) }
            Text(
                stringResource(R.string.landing_accounts),
                Modifier.padding(16.dp),
                color = Palette.FgMuted,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

@Composable
private fun TopBar(onSignIn: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .drawBehind { bottomLine(Palette.Line, 1.dp.toPx()) }
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Image(painterResource(R.drawable.ic_brand), null, Modifier.size(26.dp))
        Text(
            stringResource(R.string.app_name).uppercase(),
            Modifier.weight(1f),
            color = Palette.Fg,
            style = MaterialTheme.typography.titleSmall.copy(fontSize = 15.sp)
        )
        SnButton(stringResource(R.string.landing_sign_in), onSignIn, kind = Kind.Link)
    }
}

/** The incident playing out step by step, then held on its code, then again. */
@Composable
private fun Chain(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    // Animations off in the system settings: the whole incident at once, standing still
    val still = remember {
        Settings.Global.getFloat(
            context.contentResolver,
            Settings.Global.ANIMATOR_DURATION_SCALE,
            1f
        ) == 0f
    }
    var shown by remember { mutableIntStateOf(if (still) STEPS.size + 1 else 0) }
    val trace = remember { Animatable(if (still) 1f else 0f) }
    if (!still) {
        LaunchedEffect(Unit) {
            while (true) {
                shown = 0
                trace.snapTo(0f)
                delay(400)
                launch { trace.animateTo(1f, tween(2400, easing = EaseOut)) }
                repeat(STEPS.size + 1) {
                    delay(STEP_MS)
                    shown = it + 1
                }
                delay(HOLD_MS)
            }
        }
    }

    Column(
        modifier
            .fillMaxWidth()
            .border(1.dp, Palette.Line)
            .background(Palette.Inset.copy(alpha = 0.88f))
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                stringResource(R.string.landing_example),
                Modifier.weight(1f),
                color = Palette.FgSoft,
                style = MaterialTheme.typography.bodySmall
            )
            Live(still)
        }
        HorizontalDivider(thickness = 1.dp, color = Palette.Line)
        Box(Modifier.fillMaxWidth().height(72.dp).padding(horizontal = 12.dp, vertical = 6.dp)) {
            Trace(trace.value, Modifier.fillMaxSize())
            Row(verticalAlignment = Alignment.Bottom) {
                Text("128", color = Palette.Fg, style = Mono.copy(fontSize = 20.sp))
                Text(
                    stringResource(R.string.landing_bpm),
                    Modifier.padding(start = 4.dp, bottom = 2.dp),
                    color = Palette.FgMuted,
                    style = Mono.copy(fontSize = 11.sp)
                )
            }
        }
        HorizontalDivider(thickness = 1.dp, color = Palette.Line)
        Column(Modifier.padding(vertical = 6.dp)) {
            STEPS.forEachIndexed { i, (at, text) ->
                val alpha by animateFloatAsState(
                    if (i < shown) 1f else 0.14f,
                    tween(500, easing = EaseOut),
                    label = "step"
                )
                Row(Modifier.alpha(alpha).padding(horizontal = 12.dp, vertical = 5.dp)) {
                    Text(
                        at,
                        Modifier.width(66.dp),
                        color = Palette.FgMuted,
                        style = Mono.copy(fontSize = 11.sp, lineHeight = 18.sp)
                    )
                    Text(
                        stringResource(text),
                        color = if (text in QUOTES) Palette.Fg else Palette.FgSoft,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
        }
        val verdict by animateFloatAsState(
            if (shown > STEPS.size) 1f else 0f,
            tween(600, easing = EaseOut),
            label = "verdict"
        )
        Row(
            Modifier
                .fillMaxWidth()
                .alpha(verdict)
                .background(Palette.Rosu.copy(alpha = 0.12f))
                .drawBehind {
                    drawLine(Palette.Rosu, Offset.Zero, Offset(size.width, 0f), 2.dp.toPx())
                }
                .padding(horizontal = 12.dp, vertical = 11.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(9.dp).background(Palette.Rosu))
            Text(
                stringResource(R.string.landing_red),
                color = Palette.RosuFg,
                style = Mono.copy(fontSize = 12.sp, letterSpacing = 0.05.em)
            )
            Text(
                stringResource(R.string.landing_red_note),
                color = Color(0xFFFFD8D3),
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

/** The blinking square and ÎN DESFĂȘURARE. */
@Composable
private fun Live(still: Boolean) {
    val blink = if (still) {
        1f
    } else {
        rememberInfiniteTransition(label = "live").animateFloat(
            1f,
            0.2f,
            infiniteRepeatable(tween(600), RepeatMode.Reverse),
            label = "blink"
        ).value
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(7.dp).alpha(blink).background(Palette.Rosu))
        Text(
            stringResource(R.string.landing_live),
            Modifier.padding(start = 6.dp),
            color = Palette.RosuFg,
            style = Mono.copy(fontSize = 11.sp, letterSpacing = 0.04.em)
        )
    }
}

// The pulse on a 480 × 92 grid, as on the web landing page: calm, then racing from x = 236.
private val CALM = listOf(
    0 to 60, 120 to 60, 130 to 52, 138 to 64, 146 to 60, 210 to 60, 220 to 54, 228 to 63, 236 to 60
)
private val RACING = listOf(
    236 to 60, 262 to 60, 270 to 40, 278 to 70, 290 to 12, 302 to 84, 312 to 60, 332 to 60,
    340 to 34, 348 to 74, 358 to 18, 368 to 80, 378 to 60, 404 to 60, 412 to 38, 420 to 72,
    430 to 22, 440 to 78, 450 to 60, 480 to 60
)

/** The calm line, and the racing one drawn up to [progress]. */
@Composable
private fun Trace(progress: Float, modifier: Modifier = Modifier) {
    val measure = remember { PathMeasure() }
    Canvas(modifier) {
        fun path(points: List<Pair<Int, Int>>) = Path().apply {
            points.forEachIndexed { i, (x, y) ->
                val px = x / 480f * size.width
                val py = y / 92f * size.height
                if (i == 0) moveTo(px, py) else lineTo(px, py)
            }
        }
        drawPath(path(CALM), Palette.LineStrong, style = Stroke(2.dp.toPx()))
        val racing = path(RACING)
        measure.setPath(racing, false)
        val drawn = Path()
        measure.getSegment(0f, measure.length * progress, drawn, true)
        drawPath(
            drawn,
            Palette.Rosu,
            style = Stroke(2.4.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
        )
    }
}

@Composable
private fun DoesRow(item: Does) {
    Row(
        Modifier
            .fillMaxWidth()
            .drawBehind { bottomLine(Palette.Line, 1.dp.toPx()) }
            .padding(horizontal = 16.dp, vertical = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Icon(
            painterResource(item.icon),
            null,
            Modifier.padding(top = 2.dp).size(22.dp),
            tint = item.tint
        )
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                stringResource(item.title),
                color = Palette.Fg,
                style = MaterialTheme.typography.titleSmall.copy(fontSize = 16.sp)
            )
            Text(
                stringResource(item.text),
                color = Palette.FgMuted,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}

private fun DrawScope.bottomLine(color: Color, width: Float) =
    drawLine(color, Offset(0f, size.height), Offset(size.width, size.height), width)

/** A faint grid fading out from the top right, under a red glow: the web page's backdrop. */
private fun DrawScope.backdrop() {
    val step = 32.dp.toPx()
    val grid = Palette.Line.copy(alpha = 0.32f)
    var x = 0f
    while (x < size.width) {
        drawLine(grid, Offset(x, 0f), Offset(x, size.height), 1f)
        x += step
    }
    var y = 0f
    while (y < size.height) {
        drawLine(grid, Offset(0f, y), Offset(size.width, y), 1f)
        y += step
    }
    val corner = Offset(size.width * 0.85f, size.height * 0.08f)
    drawRect(
        Brush.radialGradient(
            0f to Color.Transparent,
            1f to Palette.Canvas,
            center = corner,
            radius = size.width * 0.95f
        )
    )
    val glow = size.width * 0.85f
    drawCircle(
        Brush.radialGradient(
            listOf(Palette.Rosu.copy(alpha = 0.16f), Color.Transparent),
            center = Offset(size.width, 0f),
            radius = glow
        ),
        radius = glow,
        center = Offset(size.width, 0f)
    )
}
