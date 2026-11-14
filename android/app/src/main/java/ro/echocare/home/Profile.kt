package ro.echocare.home

import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import ro.echocare.R
import ro.echocare.auth.ROLE_LABELS
import ro.echocare.auth.Screen
import ro.echocare.push.notificationsAllowed
import ro.echocare.ui.Chip
import ro.echocare.ui.Kind
import ro.echocare.ui.SectionLabel
import ro.echocare.ui.SnButton
import ro.echocare.ui.Tone
import ro.echocare.ui.formatPhone
import ro.echocare.ui.initials
import ro.echocare.ui.theme.Mono
import ro.echocare.ui.theme.Palette

/** What each role's home shows, one line under its name on the profile page. */
private val ROLE_LINES = mapOf(
    "das" to R.string.role_line_das,
    "medic" to R.string.role_line_medic,
    "caregiver" to R.string.role_line_caregiver,
    "senior" to R.string.role_line_senior
)

/**
 * The profile page (design 2026-11-13 medic home): who is signed in, the roles they may switch
 * between in one tap, whether alerts reach this phone, and *Ieșire*. [phone] comes from the
 * Firebase sign-in; null hides it.
 */
@Composable
fun ProfileScreen(
    home: Screen.Home,
    phone: String?,
    onBack: () -> Unit,
    onPickRole: (String) -> Unit,
    onSignOut: () -> Unit,
    onOpenNode: (() -> Unit)? = null
) {
    // Its own square would open this page again
    CompositionLocalProvider(LocalOpenProfile provides null) {
        HomeScaffold(stringResource(R.string.profile), onBack = onBack, menu = {}) {
            Column(
                Modifier
                    .verticalScroll(rememberScrollState())
                    .fillMaxWidth()
                    .wrapContentWidth(Alignment.CenterHorizontally)
                    .widthIn(max = 600.dp)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Who(home.displayName, phone)
                SectionLabel(stringResource(R.string.profile_role), Modifier.padding(top = 16.dp))
                home.roles.forEach { role ->
                    RoleRow(role, current = role == home.role) { onPickRole(role) }
                }
                SectionLabel(stringResource(R.string.notifications), Modifier.padding(top = 16.dp))
                Alerts()
                // The home node is the senior's (UC-15): only her phone relays it
                if (onOpenNode != null && "senior" in home.roles) {
                    SectionLabel(stringResource(R.string.node_title), Modifier.padding(top = 16.dp))
                    SnButton(
                        stringResource(R.string.node_connect),
                        onOpenNode,
                        Modifier.fillMaxWidth()
                    )
                }
                SnButton(
                    stringResource(R.string.sign_out),
                    onSignOut,
                    Modifier
                        .fillMaxWidth()
                        .padding(top = 24.dp),
                    kind = Kind.Danger
                )
            }
        }
    }
}

@Composable
private fun Who(name: String, phone: String?) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        initials(name).takeIf { it.isNotEmpty() }?.let {
            Box(
                Modifier
                    .size(56.dp)
                    .background(Palette.Card)
                    .border(1.dp, Palette.LineStrong),
                contentAlignment = Alignment.Center
            ) {
                Text(it, style = MaterialTheme.typography.titleLarge)
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(name, style = MaterialTheme.typography.titleLarge)
            phone?.let { Text(formatPhone(it), color = Palette.FgMuted, style = Mono) }
        }
    }
}

/** One role: the current one marked and still; another switches to it on a tap. */
@Composable
private fun RoleRow(role: String, current: Boolean, onPick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(Palette.Card)
            .border(2.dp, if (current) Palette.Link else Palette.Card)
            .then(
                if (current) Modifier else Modifier.clickable(role = Role.Button, onClick = onPick)
            )
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                stringResource(ROLE_LABELS.getValue(role)),
                style = MaterialTheme.typography.titleMedium
            )
            Text(
                stringResource(ROLE_LINES.getValue(role)),
                color = Palette.FgMuted,
                style = MaterialTheme.typography.bodyMedium
            )
        }
        if (current) {
            Chip(stringResource(R.string.role_active), Tone.Link)
        } else {
            Text("→", color = Palette.Link, style = MaterialTheme.typography.titleMedium)
        }
    }
}

/** Whether alerts reach this phone, re-read on return from the settings; off opens them. */
@Composable
private fun Alerts() {
    val context = LocalContext.current
    var allowed by remember { mutableStateOf(notificationsAllowed(context)) }
    LifecycleResumeEffect(Unit) {
        allowed = notificationsAllowed(context)
        onPauseOrDispose {}
    }
    Row(
        Modifier
            .fillMaxWidth()
            .background(Palette.Card)
            .then(
                if (allowed) {
                    Modifier
                } else {
                    Modifier.clickable(role = Role.Button) {
                        context.startActivity(
                            Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                                .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                        )
                    }
                }
            )
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            stringResource(R.string.notifications_device),
            Modifier.weight(1f),
            style = MaterialTheme.typography.bodyMedium
        )
        if (allowed) {
            Chip(stringResource(R.string.notifications_state_on), Tone.Verde)
        } else {
            Chip(stringResource(R.string.notifications_state_off), Tone.Galben)
        }
    }
}
