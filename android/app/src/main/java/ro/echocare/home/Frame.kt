package ro.echocare.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.delay
import ro.echocare.BuildConfig
import ro.echocare.R
import ro.echocare.ui.Banner
import ro.echocare.ui.Kind
import ro.echocare.ui.Rule
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.SquareIconButton
import ro.echocare.ui.Tone
import ro.echocare.ui.theme.Palette

// What every signed-in screen is built from (seniors §8.2).

/** The frame every signed-in screen shares: a title, a back arrow or none, and a menu. */
@Composable
fun HomeScaffold(
    title: String,
    onBack: (() -> Unit)?,
    menu: @Composable () -> Unit,
    content: @Composable () -> Unit
) {
    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = Palette.Canvas,
        topBar = { TopBar(title, onBack, menu) }
    ) { innerPadding ->
        Box(Modifier.fillMaxSize().padding(innerPadding)) { content() }
    }
}

/** The dashboard's header on a phone: brand over the title, square buttons, a 2dp rule. */
@Composable
private fun TopBar(title: String, onBack: (() -> Unit)?, menu: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(Palette.Subtle)
            .statusBarsPadding()
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (onBack != null) {
                SquareIconButton(
                    painterResource(R.drawable.ic_arrow_back),
                    stringResource(R.string.back),
                    onBack
                )
            }
            Column(Modifier.weight(1f)) {
                SectionLabel(stringResource(R.string.app_name))
                Text(
                    title,
                    Modifier.semantics { heading() },
                    style = MaterialTheme.typography.titleLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            menu()
        }
        Rule()
    }
}

/** Reads when the screen appears, then every REREAD_SECONDS while it is in front (06 §3). */
@Composable
fun RereadWhileShown(reread: () -> Unit) {
    val owner = LocalLifecycleOwner.current
    val latest by rememberUpdatedState(reread)
    LaunchedEffect(owner) {
        owner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                latest()
                delay(BuildConfig.REREAD_SECONDS.seconds)
            }
        }
    }
}

/** What [load] shows (seniors §8.2). A failure that ends the session is handed to [onSessionEnd]. */
@Composable
fun <T> LoadBody(
    load: Load<T>,
    onRetry: () -> Unit,
    onSessionEnd: (Failure) -> Unit,
    content: @Composable (T) -> Unit
) {
    val ended = (load as? Load.Failed)?.failure?.takeIf { it.endsSession }
    LaunchedEffect(ended) { ended?.let(onSessionEnd) }
    when (load) {
        Load.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = Palette.FgMuted)
        }

        is Load.Ready -> Column(Modifier.fillMaxSize()) {
            // The last data stays under the banner (06 §1)
            if (load.offline) Banner(stringResource(R.string.offline_banner), Tone.Galben)
            content(load.value)
        }

        is Load.Failed -> when (load.failure) {
            Failure.NoConnection -> Message(stringResource(R.string.no_connection)) {
                SnButton(stringResource(R.string.retry), onRetry, kind = Kind.Link)
            }

            Failure.NotFound -> Message(stringResource(R.string.not_found))

            Failure.NotAllowed -> Message(stringResource(R.string.not_allowed))

            // The session is ending: sign-in replaces this screen.
            Failure.SignedOut, Failure.NotRegistered -> {}
        }
    }
}

/** One sentence, flush left as everything on the dashboard, with an optional action under it. */
@Composable
fun Message(text: String, action: @Composable () -> Unit = {}) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(text, color = Palette.FgMuted, style = MaterialTheme.typography.bodyLarge)
        action()
    }
}
