package ro.echocare

import android.app.Application
import dagger.hilt.android.HiltAndroidApp
import ro.echocare.push.createAlertChannel

// Hilt's root (auth-layer AL16).
@HiltAndroidApp
class EchoCareApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // Before any alert arrives, the tray's included (04 §6)
        createAlertChannel(this)
    }
}
