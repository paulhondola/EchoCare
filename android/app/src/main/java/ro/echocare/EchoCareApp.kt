package ro.echocare

import android.app.Application
import dagger.hilt.android.HiltAndroidApp
import ro.echocare.push.createAlertChannel
import ro.echocare.push.createNoticeChannel

// Hilt's root (auth-layer AL16).
@HiltAndroidApp
class EchoCareApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // Before any alert arrives, the tray's included (04 §6)
        createAlertChannel(this)
        createNoticeChannel(this)
    }
}
