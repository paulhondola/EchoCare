package bia.sentinela.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import bia.sentinela.BuildConfig
import bia.sentinela.R
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.delay

// What every signed-in screen is built from (seniors §8.2).

/** The frame every signed-in screen shares: a title, a back arrow or none, and a menu. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScaffold(
    title: String,
    onBack: (() -> Unit)?,
    menu: @Composable () -> Unit,
    content: @Composable () -> Unit
) {
    Scaffold(
        modifier = Modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) {
                            Icon(
                                painterResource(R.drawable.ic_arrow_back),
                                stringResource(R.string.back)
                            )
                        }
                    }
                },
                actions = { menu() }
            )
        }
    ) { innerPadding ->
        Box(Modifier.fillMaxSize().padding(innerPadding)) { content() }
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
            CircularProgressIndicator()
        }

        is Load.Ready -> Column(Modifier.fillMaxSize()) {
            if (load.offline) {
                Text(
                    stringResource(R.string.offline_banner),
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.labelLarge,
                    textAlign = TextAlign.Center
                )
            }
            content(load.value)
        }

        is Load.Failed -> when (load.failure) {
            Failure.NoConnection -> Message(stringResource(R.string.no_connection)) {
                Button(onRetry) { Text(stringResource(R.string.retry)) }
            }

            Failure.NotFound -> Message(stringResource(R.string.not_found))

            Failure.NotAllowed -> Message(stringResource(R.string.not_allowed))

            // The session is ending: sign-in replaces this screen.
            Failure.SignedOut, Failure.NotRegistered -> {}
        }
    }
}

/** One centred sentence, with an optional action under it. */
@Composable
fun Message(text: String, action: @Composable () -> Unit = {}) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(text, textAlign = TextAlign.Center)
        action()
    }
}
