package ro.echocare.wear.presentation

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.wear.compose.material3.AppScaffold
import ro.echocare.wear.monitoring.MonitoringService
import ro.echocare.wear.presentation.theme.EchoCareTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The sensor test (S5, S13) is watched for minutes at a time
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContent {
            EchoCareTheme {
                AppScaffold {
                    val fall by MonitoringService.fallPrompt.collectAsState()
                    val f = fall
                    if (f != null) {
                        AreYouOkScreen(
                            fallId = f.id,
                            measuredAt = f.measuredAt,
                            onDone = { MonitoringService.fallPrompt.value = null }
                        )
                    } else {
                        SensorTestScreen()
                    }
                }
            }
        }
    }
}
