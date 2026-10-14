package bia.sentinela.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import bia.sentinela.R
import bia.sentinela.auth.Screen
import bia.sentinela.ui.SquareIconButton
import bia.sentinela.ui.theme.Palette

/**
 * The signed-in app: the role's home and what opens from it (seniors §8.2). Permissions are
 * FastAPI's; this only picks screens (G3).
 */
@Composable
fun HomeNav(
    home: Screen.Home,
    onSwitchRole: () -> Unit,
    onSignOut: () -> Unit,
    onSessionEnd: (Failure) -> Unit
) {
    // A new graph for a new role, so that role's home is the start destination.
    key(home.role) {
        val nav = rememberNavController()
        val menu: @Composable () -> Unit = { HomeMenu(home.canSwitch, onSwitchRole, onSignOut) }
        NavHost(nav, startDestination = homeFor(home.role)) {
            composable<SeniorsRoute> {
                SeniorsScreen(
                    title = if (home.role ==
                        "medic"
                    ) {
                        R.string.medic_home
                    } else {
                        R.string.caregiver_home
                    },
                    menu = menu,
                    onOpen = { nav.navigate(SeniorRoute(it)) },
                    onSessionEnd = onSessionEnd
                )
            }
            composable<SeniorRoute> { entry ->
                SeniorScreen(
                    id = entry.toRoute<SeniorRoute>().id,
                    onBack = { nav.popBackStack() },
                    menu = {},
                    onSessionEnd = onSessionEnd
                )
            }
            composable<OwnRoute> {
                SeniorScreen(id = null, onBack = null, menu = menu, onSessionEnd = onSessionEnd)
            }
            composable<IncidentsRoute> {
                HomeScaffold(stringResource(R.string.role_das), onBack = null, menu = menu) {
                    Message(stringResource(R.string.no_incidents))
                }
            }
        }
    }
}

/** *Schimbă rolul*, when there are several roles, and *Ieșire* (auth-layer §8.2). */
@Composable
private fun HomeMenu(canSwitch: Boolean, onSwitchRole: () -> Unit, onSignOut: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    // The Box anchors the menu to the button
    Box {
        SquareIconButton(
            painterResource(R.drawable.ic_more_vert),
            stringResource(R.string.menu),
            onClick = { open = true }
        )
        DropdownMenu(
            expanded = open,
            onDismissRequest = { open = false },
            containerColor = Palette.Subtle,
            border = BorderStroke(1.dp, Palette.Line)
        ) {
            if (canSwitch) {
                MenuItem(stringResource(R.string.change_role)) {
                    open = false
                    onSwitchRole()
                }
            }
            MenuItem(stringResource(R.string.sign_out)) {
                open = false
                onSignOut()
            }
        }
    }
}

@Composable
private fun MenuItem(text: String, onClick: () -> Unit) {
    DropdownMenuItem(
        text = { Text(text, color = Palette.Fg, style = MaterialTheme.typography.labelLarge) },
        onClick = onClick
    )
}
