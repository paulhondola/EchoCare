package ro.echocare.home

import androidx.navigation.NavHostController
import androidx.navigation.compose.ComposeNavigator
import androidx.navigation.compose.composable
import androidx.navigation.createGraph
import androidx.navigation.toRoute
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.junit.runner.RunWith

// 04 §6: a tapped alert opens its own page. On a device: the back stack's reuse of an entry, and
// with it the entry's ViewModel, is Navigation's own behaviour.
@RunWith(AndroidJUnit4::class)
class AlertNavTest {
    private fun onIncidentA(check: NavHostController.() -> Unit) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.runOnMainSync {
            NavHostController(instrumentation.targetContext).apply {
                navigatorProvider.addNavigator(ComposeNavigator())
                graph = createGraph(startDestination = IncidentsRoute) {
                    composable<IncidentsRoute> {}
                    composable<IncidentRoute> {}
                }
                navigate(IncidentRoute("a"))
                check()
            }
        }
    }

    private fun NavHostController.top() = currentBackStackEntry!!.toRoute<IncidentRoute>()

    @Test
    fun anAlertForAnotherIncidentGetsItsOwnEntry() = onIncidentA {
        // A reused entry keeps its id, and so the ViewModel still reading incident a
        val onA = currentBackStackEntry!!.id
        openAlert(IncidentRoute("b"))
        assertEquals(IncidentRoute("b"), top())
        assertNotEquals(onA, currentBackStackEntry!!.id)
        assertEquals(onA, previousBackStackEntry!!.id)
    }

    @Test
    fun anAlertForThePageInFrontAddsNothing() = onIncidentA {
        val onA = currentBackStackEntry!!.id
        openAlert(IncidentRoute("a"))
        assertEquals(onA, currentBackStackEntry!!.id)
        assertEquals(IncidentRoute("a"), top())
    }
}
