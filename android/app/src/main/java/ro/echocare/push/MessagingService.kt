package ro.echocare.push

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import ro.echocare.EchoCareApi

/**
 * Firebase push (04 §6). With the app closed, Firebase shows an alert in the tray itself, and a
 * refresh arrives here with no screen to update. With it open, both arrive here.
 */
@AndroidEntryPoint
class MessagingService : FirebaseMessagingService() {
    @Inject lateinit var auth: FirebaseAuth

    @Inject lateinit var api: EchoCareApi

    /**
     * A new token for this device: the API learns it now if someone is signed in (Q19). Firebase
     * calls this on its own background thread, so waiting here blocks no screen.
     */
    override fun onNewToken(token: String) {
        if (auth.currentUser == null) return
        saveBeforeReturning { api.savePushToken(token) }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        // A token still alive after an offline sign-out, until the next start deletes it
        if (auth.currentUser == null) return
        val push = pushFrom(message.data) ?: return
        if (push is Push.Alert) showAlert(this, message.data)
        if (push is Push.Notice) showNotice(this, message.data)
        // An alert changed something too: the open screen re-reads either way
        Refreshes.signal()
    }
}
