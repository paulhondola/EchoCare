package ro.echocare.wear.presentation

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.wear.compose.material3.AppScaffold
import kotlinx.coroutines.flow.update
import ro.echocare.wear.monitoring.MonitoringService
import ro.echocare.wear.presentation.theme.EchoCareTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // UC-09 §1: monitoring runs the whole time the app is open; the screen stays on for the demo
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        // Fall full-screen intent needs to wake the watch and show over the lock screen
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        setContent {
            EchoCareTheme {
                AppScaffold {
                    // „Sunteți bine?” first, then „help is coming”, then home (design 2026-11-14)
                    val fall by MonitoringService.fallPrompt.collectAsState()
                    val alert by MonitoringService.alert.collectAsState()
                    val f = fall
                    val a = alert
                    if (f != null) {
                        AreYouOkScreen(
                            fallId = f.id,
                            measuredAt = f.measuredAt,
                            type = f.type,
                            snapshot = f.snapshot,
                            onDone = {
                                MonitoringService.fallPrompt.value = null
                                MonitoringService.dismissFallNotification(this@MainActivity)
                            }
                        )
                    } else if (a != null) {
                        HelpComingScreen(a) {
                            MonitoringService.alert.update { if (it?.id == a.id) null else it }
                        }
                    } else {
                        SeniorHomeScreen()
                    }
                }
            }
        }
    }
}
