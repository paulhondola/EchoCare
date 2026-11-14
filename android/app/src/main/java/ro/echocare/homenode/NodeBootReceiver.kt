package ro.echocare.homenode

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Starts the home node's relay again after the phone restarts, so the node is not left
 * talking to nobody until the senior opens the app (P20, UC-13). A connected-device service
 * may start from boot; nothing starts without a saved node and Bluetooth permission.
 */
class NodeBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) NodeService.start(context)
    }
}
