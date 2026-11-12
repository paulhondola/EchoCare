package ro.echocare.push

import android.content.Context
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.WearableListenerService
import com.google.firebase.auth.FirebaseAuth
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import ro.echocare.CheckInForm
import ro.echocare.EchoCareApi
import ro.echocare.EventForm
import ro.echocare.EventSnapshotForm
import ro.echocare.home.lastKnownLocation
import ro.echocare.shared.CheckInMessage
import ro.echocare.shared.DataLayer
import ro.echocare.shared.EventMessage
import ro.echocare.shared.EventSnapshot

internal fun EventSnapshot.toForm(): EventSnapshotForm? = if (this == EventSnapshot.EMPTY) {
    null
} else {
    EventSnapshotForm(
        pulse = pulse,
        restingBaseline = restingBaseline,
        moving = moving,
        minutesWithoutSteps = minutesWithoutSteps,
        battery = battery
    )
}

/** Watch → phone mapping; separated so JVM tests can exercise it without Android. */
internal fun EventMessage.toEventForm(
    latitude: Double? = null,
    longitude: Double? = null,
    locationAccuracyM: Double? = null
): EventForm = EventForm(
    id = id,
    type = type,
    measuredAt = measuredAt,
    source = "watch",
    snapshot = snapshot.toForm(),
    latitude = latitude,
    longitude = longitude,
    locationAccuracyM = locationAccuracyM
)

internal fun CheckInMessage.toCheckInForm(): CheckInForm = CheckInForm(
    measuredAt = measuredAt,
    battery = battery,
    worn = worn,
    lastPulse = lastPulse
)

/**
 * Receives Data Layer messages from the watch (04 §3, UC-09, UC-13) and forwards them to FastAPI.
 * The watch is not standalone (G5); every API call goes through here.
 */
@AndroidEntryPoint
class WearListenerService : WearableListenerService() {
    @Inject lateinit var auth: FirebaseAuth

    @Inject lateinit var api: EchoCareApi

    override fun onMessageReceived(event: MessageEvent) {
        if (auth.currentUser == null) return
        CoroutineScope(Dispatchers.IO).launch {
            when (event.path) {
                DataLayer.CHECK_IN -> {
                    val form = CheckInMessage.fromBytes(event.data).toCheckInForm()
                    runCatching { api.checkIn(form) }
                }
                DataLayer.EVENT -> {
                    val msg = EventMessage.fromBytes(event.data)
                    val here = lastKnownLocation(this@WearListenerService as Context)
                    val form = msg.toEventForm(
                        latitude = here?.latitude,
                        longitude = here?.longitude,
                        locationAccuracyM = here?.accuracy?.toDouble()
                    )
                    val ok = runCatching { api.sendEvent(form) }.isSuccess
                    // Tell the watch to drop this id from its resend queue (04 §3)
                    if (ok) ackToWatch(event.sourceNodeId, msg.id)
                }
            }
        }
    }

    private fun ackToWatch(nodeId: String, eventId: String) {
        Wearable.getMessageClient(this)
            .sendMessage(nodeId, "${DataLayer.RECEIVED}/$eventId", ByteArray(0))
    }
}
