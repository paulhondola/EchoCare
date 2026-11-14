package ro.echocare.homenode

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.location.Location
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.firebase.auth.FirebaseAuth
import dagger.hilt.android.AndroidEntryPoint
import java.time.Instant
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ro.echocare.EchoCareApi
import ro.echocare.EventForm
import ro.echocare.R
import ro.echocare.home.lastKnownLocation

/**
 * Relays the home node to FastAPI (UC-15, UC-16, 04 §3): room readings, SOS presses and falls go
 * up; the room state, the light and the acknowledgements go back down. A foreground service, so
 * it keeps the Bluetooth link while the app is in the background (spike S12).
 *
 * The node never reaches the internet; this service is its only way out (P20).
 */
@AndroidEntryPoint
class NodeService :
    Service(),
    NodeLink.Listener {
    @Inject lateinit var auth: FirebaseAuth

    @Inject lateinit var api: EchoCareApi

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var link: NodeLink? = null
    private var lastLight: String? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val address = NodePrefs.address(this)
        if (address == null || !bluetoothAllowed(this)) {
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(
            NOTIFICATION_ID,
            notification(),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
        )
        if (link == null) {
            link = NodeLink(this, address, this).also { it.connect() }
            _status.value = Status(address, connected = false)
            scope.launch { keepLightCurrent() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        link?.close()
        link = null
        scope.cancel()
        _status.value = null
        super.onDestroy()
    }

    // --- from the node -------------------------------------------------------------------

    override fun onConnected(connected: Boolean) {
        _status.value = _status.value?.copy(connected = connected)
        if (connected) {
            lastLight = null // write it again: the node may have restarted
            scope.launch { pushLight() }
        }
    }

    override fun onNotified(characteristic: UUID, text: String) {
        if (auth.currentUser == null) return
        scope.launch {
            when (characteristic) {
                NodeUuids.ROOM_READING -> parseReading(text)?.let { relayReading(it) }
                NodeUuids.SOS_PRESS -> {
                    val sos = parseSos(text) ?: return@launch
                    relay(sos.id) { now, here ->
                        sos.toEventForm(now, here?.latitude, here?.longitude, accuracy(here))
                    }
                }
                NodeUuids.FALL -> {
                    val fall = parseFall(text) ?: return@launch
                    relay(fall.id) { now, here ->
                        fall.toEventForm(now, here?.latitude, here?.longitude, accuracy(here))
                    }
                }
                NodeUuids.MOTION -> Unit // FastAPI learns motion from the next reading (04 §3)
            }
        }
    }

    private suspend fun relayReading(reading: NodeReading) {
        _status.value = _status.value?.copy(temperature = reading.temperature)
        val answer = runCatching { api.sendRoomReading(reading.toForm(Instant.now())) }
            .onFailure { Log.w(TAG, "room reading not sent", it) }
            .getOrNull() ?: return
        _status.value = _status.value?.copy(roomState = answer.roomState)
        link?.write(NodeUuids.ROOM_STATE, answer.roomState)
    }

    private fun accuracy(here: Location?): Double? = here?.accuracy?.toDouble()

    /** An event goes to FastAPI; once recorded, the node hears its id and stops resending. */
    private suspend fun relay(id: String, form: (Instant, Location?) -> EventForm) {
        val here = lastKnownLocation(this)
        val sent = runCatching { api.sendEvent(form(Instant.now(), here)) }
            .onFailure { Log.w(TAG, "event $id not sent", it) }
            .isSuccess
        if (sent) {
            link?.write(NodeUuids.ACKNOWLEDGE, id)
            pushLight()
        }
    }

    // --- to the node ---------------------------------------------------------------------

    private suspend fun keepLightCurrent() {
        while (scope.isActive) {
            pushLight()
            delay(LIGHT_EVERY_MS)
        }
    }

    /** The senior's code, or `call` while a call rings, written whenever it changes (04 §3). */
    private suspend fun pushLight() {
        if (auth.currentUser == null || link?.connected != true) return
        val light = runCatching {
            val own = api.seniors("senior").firstOrNull() ?: return
            val page = api.senior(own.id)
            lightFor(page.code, page.callInProgress)
        }.getOrNull() ?: return
        if (light != lastLight && link?.write(NodeUuids.LIGHT, light) == true) lastLight = light
    }

    private fun notification() = NotificationCompat.Builder(this, CHANNEL)
        .setSmallIcon(R.drawable.ic_notification)
        .setContentTitle(getString(R.string.node_title))
        .setContentText(getString(R.string.node_notification))
        .setOngoing(true)
        .setPriority(NotificationCompat.PRIORITY_LOW)
        .build()

    data class Status(
        val address: String,
        val connected: Boolean,
        val temperature: Double? = null,
        val roomState: String? = null
    )

    companion object {
        private const val TAG = "NodeService"
        private const val CHANNEL = "home_node"
        private const val NOTIFICATION_ID = 40
        private const val LIGHT_EVERY_MS = 20_000L

        private val _status = MutableStateFlow<Status?>(null)

        /** What the node screen shows: null while the service is not running. */
        val status: StateFlow<Status?> = _status.asStateFlow()

        fun bluetoothAllowed(context: Context): Boolean =
            listOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN)
                .all {
                    ContextCompat.checkSelfPermission(context, it) ==
                        PackageManager.PERMISSION_GRANTED
                }

        fun createChannel(context: Context) {
            val channel = NotificationChannel(
                CHANNEL,
                context.getString(R.string.node_title),
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = context.getString(R.string.node_notification) }
            context.getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }

        /** Starts the relay when a node is saved and Bluetooth is allowed; else does nothing. */
        fun start(context: Context) {
            if (NodePrefs.address(context) == null || !bluetoothAllowed(context)) return
            createChannel(context)
            context.startForegroundService(Intent(context, NodeService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, NodeService::class.java))
        }
    }
}
