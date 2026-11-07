package ro.echocare.wear.presentation

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.wear.compose.material3.AppScaffold
import ro.echocare.wear.presentation.theme.EchoCareTheme

class MainActivity : ComponentActivity() {

    // Null means no fall prompt; a non-null pair is (fallId, measuredAt)
    private var fall by mutableStateOf<Pair<String, String>?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The sensor test (S5, S13) is watched for minutes at a time
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        fall = fallFromIntent(intent)
        setContent {
            EchoCareTheme {
                AppScaffold {
                    val f = fall
                    if (f != null) {
                        AreYouOkScreen(
                            fallId = f.first,
                            measuredAt = f.second,
                            onDone = { fall = null }
                        )
                    } else {
                        SensorTestScreen()
                    }
                }
            }
        }
    }

    // MonitoringService brings the prompt to the front with a new intent while the activity is alive
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        fall = fallFromIntent(intent) ?: fall
    }

    companion object {
        const val EXTRA_FALL_ID = "fall_id"
        const val EXTRA_FALL_AT = "fall_at"

        fun fallFromIntent(intent: Intent?): Pair<String, String>? {
            val id = intent?.getStringExtra(EXTRA_FALL_ID) ?: return null
            val at = intent.getStringExtra(EXTRA_FALL_AT) ?: return null
            return id to at
        }
    }
}
