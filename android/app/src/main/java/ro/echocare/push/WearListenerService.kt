package ro.echocare.push

import com.google.android.gms.wearable.MessageEvent
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
import ro.echocare.shared.CheckInMessage
import ro.echocare.shared.DataLayer
import ro.echocare.shared.EventMessage
import ro.echocare.shared.EventSnapshot

private fun EventSnapshot.toForm(): EventSnapshotForm? = if (this == EventSnapshot.EMPTY) {
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
                    val msg = CheckInMessage.fromBytes(event.data)
                    runCatching {
                        api.checkIn(
                            CheckInForm(
                                measuredAt = msg.measuredAt,
                                battery = msg.battery,
                                worn = msg.worn,
                                lastPulse = msg.lastPulse
                            )
                        )
                    }
                }
                DataLayer.EVENT -> {
                    val msg = EventMessage.fromBytes(event.data)
                    runCatching {
                        api.sendEvent(
                            EventForm(
                                id = msg.id,
                                type = msg.type,
                                measuredAt = msg.measuredAt,
                                snapshot = msg.snapshot.toForm()
                            )
                        )
                    }
                }
            }
        }
    }
}
