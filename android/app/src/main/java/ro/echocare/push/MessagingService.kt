package ro.echocare.push

import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import java.io.IOException
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import retrofit2.HttpException
import ro.echocare.EchoCareApi

/**
 * Firebase push (04 §6). With the app closed, Firebase shows an alert in the tray itself and drops a
 * refresh, which has no screen to update. With it open, both arrive here.
 */
@AndroidEntryPoint
class MessagingService : FirebaseMessagingService() {
    @Inject lateinit var auth: FirebaseAuth

    @Inject lateinit var api: EchoCareApi

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /** A new token for this device: the API learns it now if someone is signed in (Q19). */
    override fun onNewToken(token: String) {
        if (auth.currentUser == null) return
        scope.launch {
            try {
                api.savePushToken(token)
            } catch (e: IOException) {
                // Saved again at the next sign-in or start (AuthViewModel.loadMe)
            } catch (e: HttpException) {
            }
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val push = pushFrom(message.data) ?: return
        if (push is Push.Alert) showAlert(this, message.data)
        // An alert changed something too: the open screen re-reads either way
        Refreshes.signal()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
