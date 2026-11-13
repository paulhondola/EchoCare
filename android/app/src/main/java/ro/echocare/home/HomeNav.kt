package ro.echocare.home

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.navigation.NavController
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import ro.echocare.auth.Screen
import ro.echocare.das.IncidentScreen
import ro.echocare.das.IncidentsScreen
import ro.echocare.das.ResolveScreen
import ro.echocare.enroll.EnrollScreen
import ro.echocare.push.Push

/**
 * The signed-in app: the role's home and what opens from it (seniors §8.2). Permissions are
 * FastAPI's; this only picks screens (G3).
 */
@Composable
fun HomeNav(
    home: Screen.Home,
    phone: String?,
    onPickRole: (String) -> Unit,
    onSignOut: () -> Unit,
    onSessionEnd: (Failure) -> Unit,
    opening: Push.Alert? = null,
    onOpened: () -> Unit = {}
) {
    // A new graph for a new role, so that role's home is the start destination.
    key(home.role) {
        val nav = rememberNavController()
        // The top bar's slot holds nothing of the app's own: the profile opens from the person's
        // square, which carries role switching and Ieșire (design 2026-11-13 medic home)
        val menu: @Composable () -> Unit = {}
        // Only the medic registers seniors (04 §2): the form's entry points are theirs (seniors §9.1)
        val medic = home.role == "medic"
        var sent by rememberSaveable { mutableStateOf(false) }
        CompositionLocalProvider(
            LocalSignedIn provides home.displayName,
            LocalOpenProfile provides { nav.navigate(ProfileRoute) { launchSingleTop = true } }
        ) {
            NavHost(nav, startDestination = homeFor(home.role)) {
                composable<MedicHomeRoute> {
                    MedicHomeScreen(
                        menu = menu,
                        onMonitor = { nav.navigate(MonitorRoute) },
                        onNew = { nav.navigate(EnrollRoute()) },
                        onOpen = { nav.navigate(SeniorRoute(it)) },
                        onDraft = { nav.navigate(EnrollRoute(it)) },
                        onSessionEnd = onSessionEnd,
                        sent = sent,
                        onSentShown = { sent = false }
                    )
                }
                composable<MonitorRoute> {
                    MonitorScreen(
                        onBack = { nav.popBackStack<MonitorRoute>(inclusive = true) },
                        menu = menu,
                        onOpen = { nav.navigate(SeniorRoute(it)) },
                        onNew = { nav.navigate(EnrollRoute()) },
                        onEdit = { nav.navigate(EnrollRoute(it)) },
                        onSessionEnd = onSessionEnd
                    )
                }
                composable<SeniorsRoute> {
                    SeniorsScreen(
                        menu = menu,
                        onOpen = { nav.navigate(SeniorRoute(it.id)) },
                        onSessionEnd = onSessionEnd
                    )
                }
                composable<SeniorRoute> { entry ->
                    SeniorScreen(
                        id = entry.toRoute<SeniorRoute>().id,
                        onBack = { nav.popBackStack() },
                        menu = {},
                        onSessionEnd = onSessionEnd,
                        onEdit = if (medic) ({ nav.navigate(EnrollRoute(it)) }) else null
                    )
                }
                composable<EnrollRoute> {
                    // No profile from a form: switching role there would drop what was typed
                    CompositionLocalProvider(LocalOpenProfile provides null) {
                        EnrollScreen(
                            // Popping by route makes a second tap a no-op, never the home popped too
                            onLeave = { nav.popBackStack<EnrollRoute>(inclusive = true) },
                            onSubmitted = {
                                sent = true
                                nav.popBackStack<MedicHomeRoute>(inclusive = false)
                            },
                            onDone = { nav.toPage(it) },
                            onSessionEnd = onSessionEnd
                        )
                    }
                }
                composable<ProfileRoute> {
                    ProfileScreen(
                        home = home,
                        phone = phone,
                        // By route, as EnrollRoute: a second tap never pops the home
                        onBack = { nav.popBackStack<ProfileRoute>(inclusive = true) },
                        onPickRole = onPickRole,
                        onSignOut = onSignOut
                    )
                }
                composable<OwnRoute> {
                    SeniorScreen(id = null, onBack = null, menu = menu, onSessionEnd = onSessionEnd)
                }
                composable<IncidentsRoute> {
                    IncidentsScreen(
                        menu = menu,
                        onOpen = { nav.navigate(IncidentRoute(it)) },
                        onSessionEnd = onSessionEnd
                    )
                }
                composable<IncidentRoute> {
                    IncidentScreen(
                        // By route, as EnrollRoute: a second tap never pops the home
                        onBack = { nav.popBackStack<IncidentRoute>(inclusive = true) },
                        onResolve = { nav.navigate(ResolveRoute(it)) },
                        onSessionEnd = onSessionEnd
                    )
                }
                composable<ResolveRoute> {
                    CompositionLocalProvider(LocalOpenProfile provides null) {
                        ResolveScreen(
                            onBack = { nav.popBackStack<ResolveRoute>(inclusive = true) },
                            // Resolved incidents leave the list: back to it, past the incident's page
                            onDone = { nav.popBackStack<IncidentsRoute>(inclusive = false) },
                            onSessionEnd = onSessionEnd
                        )
                    }
                }
            }
        }
        // A tapped alert opens its senior, or for DAS its incident, over the home (04 §6)
        LaunchedEffect(opening) {
            val alert = opening ?: return@LaunchedEffect
            nav.openAlert(alertRoute(alert.seniorId, alert.incidentId, home.role))
            onOpened()
        }
    }
}

/**
 * A tapped alert's page, unless it is the one in front. Not `launchSingleTop`: that reuses the entry
 * for any route of the same type, and with it the ViewModel, which goes on reading the old id.
 */
internal fun NavController.openAlert(route: Any) {
    val top = currentBackStackEntry
    val inFront = top?.destination?.hasRoute(route::class) == true &&
        top.toRoute<Any>(route::class) == route
    if (!inFront) navigate(route)
}

/**
 * „Gata”: back to where „Editează datele” opened the form, the senior's page or Monitorizare with
 * the patient still selected (UC-12), or a new page.
 */
private fun NavController.toPage(id: String) {
    val from = previousBackStackEntry?.destination
    if (from?.hasRoute<SeniorRoute>() == true || from?.hasRoute<MonitorRoute>() == true) {
        popBackStack()
    } else {
        navigate(SeniorRoute(id)) { popUpTo<EnrollRoute> { inclusive = true } }
    }
}
