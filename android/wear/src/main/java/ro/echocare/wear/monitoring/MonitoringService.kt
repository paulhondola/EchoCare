package ro.echocare.wear.monitoring

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.BatteryManager
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.VibratorManager
import android.util.Log
import com.google.android.gms.wearable.MessageClient
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.Wearable
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import ro.echocare.shared.CheckInMessage
import ro.echocare.shared.DataLayer
import ro.echocare.shared.EventSnapshot
import ro.echocare.shared.FallDetector
import ro.echocare.shared.InactivityDetector
import ro.echocare.shared.PulseAnomaly
import ro.echocare.shared.RestingBaseline
import ro.echocare.wear.BuildConfig
import ro.echocare.wear.R
import ro.echocare.wear.presentation.MainActivity

// 50 readings a second, the rate fall detection needs (P19)
internal const val ACCELEROMETER_PERIOD_US = 20_000

/**
 * Spike S5 (06 §6): does the watch keep delivering pulse, steps and the accelerometer with the
 * screen off, and what does it cost in battery? Runs the fall detector the whole time and logs a
 * summary every minute, for `adb logcat -s SentinelaMonitor`.
 */
class MonitoringService :
    Service(),
    SensorEventListener,
    MessageClient.OnMessageReceivedListener {
    private lateinit var sensorManager: SensorManager
    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler
    private lateinit var wakeLock: PowerManager.WakeLock
    private lateinit var eventQueue: EventQueue
    private val fallDetector = FallDetector()
    private val restingBaseline = RestingBaseline()

    // Demo values from 06 §3; production uses the detector defaults (4 h inactivity)
    private val pulseAnomaly = PulseAnomaly(holdMs = if (BuildConfig.DEMO) 15_000L else 60_000L)
    private val inactivity = InactivityDetector(
        limitMs = if (BuildConfig.DEMO) 60_000L else 4 * 60 * 60_000L
    )

    // Counted on the sensor thread; logged and reset every minute
    private var minute = 0
    private var accelReadings = 0
    private var lastAccelNs = 0L
    private var maxAccelGapNs = 0L
    private var heartRateReadings = 0
    private var lastHeartRate = 0
    private var stepsAtMinuteStart = -1f
    private var lastStepCount = -1f
    private var falls = 0
    private var lastStepAtMs = -1L
    private var startedAtMs = 0L
    private var lastTickMs = 0L

    // For the check-in (ADR-006). Stays true on a watch without an off-body sensor, as before
    private var worn = true
    private var stepsAtDayStart = -1f
    private var stepDay: LocalDate? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_FORCE_ANOMALY -> {
                val type = intent.getStringExtra(EXTRA_FORCE_TYPE) ?: "high_pulse_at_rest"
                // A fabricated snapshot that looks like the real detector saw it
                raiseAnomaly(
                    type,
                    EventSnapshot(
                        pulse = if (type ==
                            "high_pulse_at_rest"
                        ) {
                            125
                        } else {
                            lastHeartRate.takeIf { it > 0 }
                        },
                        restingBaseline = restingBaseline.value(System.currentTimeMillis()),
                        moving = false,
                        minutesWithoutSteps = if (type == "inactivity") 240 else 0,
                        battery = battery()
                    )
                )
                log("forced anomaly=$type")
            }
            ACTION_SEND_EVENT -> {
                val bytes = intent.getByteArrayExtra(EXTRA_EVENT_BYTES)
                if (bytes != null) {
                    enqueueAndSend(ro.echocare.shared.EventMessage.fromBytes(bytes))
                }
            }
        }
        return START_STICKY
    }

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIFICATION_ID, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH)
        // One session per file, so it never grows past a few kilobytes an hour
        File(filesDir, LOG_FILE).delete()
        thread = HandlerThread(TAG).apply { start() }
        handler = Handler(thread.looper)
        sensorManager = getSystemService(SensorManager::class.java)
        // Before the sensors: their first reading may run the minute's tick, which needs these
        eventQueue = EventQueue(File(filesDir, "events"))
        startedAtMs = System.currentTimeMillis()
        lastTickMs = startedAtMs
        // Sensors batch their readings and wake the CPU only to hand a batch over, so it can sleep
        // in between (S5 measured ~24 %/h with it always awake)
        val accelerometer = register(Sensor.TYPE_ACCELEROMETER, ACCELEROMETER_PERIOD_US)
        listOf(
            Sensor.TYPE_HEART_RATE,
            Sensor.TYPE_STEP_COUNTER,
            Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT
        ).forEach { register(it, SensorManager.SENSOR_DELAY_NORMAL) }
        // A non-wake-up accelerometer drops what it reads while the CPU sleeps: keep it awake, as before
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "EchoCare:monitoring")
        if (accelerometer?.isWakeUpSensor != true) wakeLock.acquire(MAX_WAKE_MS)
        handler.postDelayed(::tickLoop, TICK_CHECK_MS)
        Wearable.getMessageClient(this).addListener(this)
        running.value = true
        log(
            "started battery=${battery()}% pending=${eventQueue.pending().size} " +
                "wakeLock=${wakeLock.isHeld}"
        )
        // Resend anything the phone never acked
        resendPending()
    }

    override fun onDestroy() {
        sensorManager.unregisterListener(this)
        Wearable.getMessageClient(this).removeListener(this)
        handler.removeCallbacksAndMessages(null)
        thread.quitSafely()
        if (wakeLock.isHeld) wakeLock.release()
        running.value = false
        log("stopped after minute=$minute battery=${battery()}%")
        super.onDestroy()
    }

    override fun onMessageReceived(event: MessageEvent) {
        // `/echocare/received/<id>` — the phone acked an event
        if (event.path.startsWith(DataLayer.RECEIVED)) {
            val id = event.path.substringAfterLast('/').takeIf { it.isNotEmpty() } ?: return
            eventQueue.ack(id)
            log("event acked id=$id")
        }
    }

    /** The wake-up variant when the watch has one, batched up to [BATCH_LATENCY_US]; null without the sensor. */
    private fun register(type: Int, periodUs: Int): Sensor? {
        val sensor = sensorManager.getDefaultSensor(type, true)
            ?: sensorManager.getDefaultSensor(type)
            ?: return null
        sensorManager.registerListener(this, sensor, periodUs, BATCH_LATENCY_US, handler)
        log(
            "sensor ${sensor.stringType} wakeUp=${sensor.isWakeUpSensor} fifo=${sensor.fifoMaxEventCount}"
        )
        return sensor
    }

    // Wall-clock minutes: a Handler's delay stops counting while the CPU sleeps, so the sensors'
    // batches also drive the tick
    private fun tickIfDue() {
        val now = System.currentTimeMillis()
        if (now - lastTickMs >= MINUTE_MS) {
            lastTickMs = now
            logMinute()
        }
    }

    private fun tickLoop() {
        tickIfDue()
        handler.postDelayed(::tickLoop, TICK_CHECK_MS)
    }

    override fun onSensorChanged(event: SensorEvent) {
        tickIfDue()
        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> onAcceleration(event)
            Sensor.TYPE_HEART_RATE -> {
                // Samsung reports 0 while it is still acquiring a pulse
                val bpm = event.values[0].toInt()
                if (bpm > 0) {
                    heartRateReadings++
                    lastHeartRate = bpm
                    onHeartRate(bpm)
                }
            }
            Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT -> {
                // 1.0 on the wrist, 0.0 off it
                val now = event.values[0] == 1f
                if (now != worn) {
                    worn = now
                    log("worn=$worn")
                    // Taking it off (or back on) shouldn't wait up to 15 minutes for the next check-in
                    if (minute > 0) sendCheckIn()
                }
            }
            Sensor.TYPE_STEP_COUNTER -> {
                if (stepsAtMinuteStart < 0) stepsAtMinuteStart = event.values[0]
                // shortcut: counts from the service's first reading of the day, so a restart loses the
                // morning's steps; Health Services' STEPS_DAILY if the exact daily total matters
                val today = LocalDate.now()
                if (stepDay != today) {
                    stepDay = today
                    stepsAtDayStart = event.values[0]
                }
                // Only treat it as a step if the counter actually advanced (not the first reading)
                if (lastStepCount >= 0 && event.values[0] > lastStepCount) {
                    lastStepAtMs = System.currentTimeMillis()
                    inactivity.onStep(lastStepAtMs)
                }
                lastStepCount = event.values[0]
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) = Unit

    private fun onAcceleration(event: SensorEvent) {
        accelReadings++
        // A long gap means readings were lost, for example while the CPU slept
        if (lastAccelNs > 0) maxAccelGapNs = maxOf(maxAccelGapNs, event.timestamp - lastAccelNs)
        lastAccelNs = event.timestamp
        val (x, y, z) = event.values
        if (fallDetector.onReading(
                event.timestamp / 1_000_000,
                FallDetector.accelerationG(x, y, z)
            )
        ) {
            falls++
            raiseAnomaly("fall", snapshot())
            log("fall detected in minute=${minute + 1}")
        }
    }

    /** Called for every valid heart-rate reading. Tracks the resting baseline and the pulse-at-rest rule. */
    private fun onHeartRate(bpm: Int) {
        val nowMs = System.currentTimeMillis()
        val moving = isMoving(nowMs)
        // Null until enough still readings land, so the default can't raise a false alarm
        val baseline = restingBaseline.measured(nowMs)
        restingBaseline.onReading(nowMs, bpm, moving)
        if (pulseAnomaly.onReading(nowMs, bpm, baseline, moving)) {
            pulseAnomaly.reset()
            raiseAnomaly("high_pulse_at_rest", snapshot())
            log("pulse anomaly bpm=$bpm baseline=$baseline")
        }
    }

    private fun isMoving(nowMs: Long): Boolean {
        // shortcut: steps are the only movement signal the service tracks; non-walking motion that
        // doesn't add a step reads as not-moving. Good enough for UC-09's "high pulse during a walk"
        return lastStepAtMs > 0 && nowMs - lastStepAtMs < MOVING_WINDOW_MS
    }

    private fun minutesWithoutSteps(nowMs: Long): Int =
        ((nowMs - if (lastStepAtMs < 0) startedAtMs else lastStepAtMs) / 60_000L).toInt()

    /** Null without a step counter; 0 on a new day before its first step. */
    private fun stepsToday(): Int? = when {
        stepsAtDayStart < 0 -> null
        stepDay != LocalDate.now() -> 0
        else -> (lastStepCount - stepsAtDayStart).toInt()
    }

    private fun snapshot(): EventSnapshot {
        val nowMs = System.currentTimeMillis()
        return EventSnapshot(
            pulse = if (lastHeartRate > 0) lastHeartRate else null,
            restingBaseline = restingBaseline.value(nowMs),
            moving = isMoving(nowMs),
            minutesWithoutSteps = minutesWithoutSteps(nowMs),
            battery = battery()
        )
    }

    private fun raiseAnomaly(type: String, snapshot: EventSnapshot) {
        val id = UUID.randomUUID().toString()
        getSystemService(VibratorManager::class.java).defaultVibrator
            .vibrate(VibrationEffect.createOneShot(600, VibrationEffect.DEFAULT_AMPLITUDE))
        // MainActivity observes this and shows „Sunteți bine?" — background service can't launch an activity on API 36
        fallPrompt.value = FallPrompt(id, Instant.now().toString(), type, snapshot)
        // A bright wake lock turns the screen on; the full-screen intent brings up MainActivity
        @Suppress("DEPRECATION")
        getSystemService(PowerManager::class.java)
            .newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "EchoCare:anomaly"
            ).acquire(10_000L)
        val nm = getSystemService(NotificationManager::class.java)
        log("canUseFullScreenIntent=${nm.canUseFullScreenIntent()}")
        nm.notify(FALL_NOTIFICATION_ID, fallNotification())
        startActivity(
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        )
    }

    private fun logMinute() {
        minute++
        val steps = if (stepsAtMinuteStart < 0) 0 else (lastStepCount - stepsAtMinuteStart).toInt()
        log(
            "minute=$minute accel=$accelReadings maxGapMs=${maxAccelGapNs / 1_000_000} " +
                "heartRates=$heartRateReadings lastHeartRate=$lastHeartRate steps=$steps falls=$falls battery=${battery()}%"
        )
        if (inactivity.isInactive(System.currentTimeMillis())) {
            raiseAnomaly("inactivity", snapshot())
            log("inactivity anomaly")
        }
        // 06 §3: every 15 minutes, every minute in the demo; the first right away
        if (minute == 1 || minute % CHECK_IN_MINUTES == 0) sendCheckIn()
        // The phone may have come back since the last tick; flush anything the queue still holds
        resendPending()
        accelReadings = 0
        maxAccelGapNs = 0L
        heartRateReadings = 0
        stepsAtMinuteStart = lastStepCount
        falls = 0
    }

    private fun resendPending() {
        val pending = eventQueue.pending()
        if (pending.isEmpty()) return
        log("resending ${pending.size} queued event(s)")
        pending.forEach(::sendEventToPhone)
    }

    /** Enqueue an event and try to send it. [onMessageReceived] clears it when the phone acks. */
    internal fun enqueueAndSend(msg: ro.echocare.shared.EventMessage) {
        eventQueue.enqueue(msg)
        sendEventToPhone(msg)
    }

    private fun sendEventToPhone(msg: ro.echocare.shared.EventMessage) {
        Wearable.getNodeClient(this).connectedNodes
            .addOnSuccessListener { nodes ->
                if (nodes.isEmpty()) {
                    log("event ${msg.id} skipped: no connected nodes")
                    return@addOnSuccessListener
                }
                nodes.forEach { node ->
                    Wearable.getMessageClient(this)
                        .sendMessage(node.id, DataLayer.EVENT, msg.toBytes())
                        .addOnSuccessListener { log("event ${msg.id} sent to ${node.displayName}") }
                        .addOnFailureListener {
                            log("event ${msg.id} failed to ${node.displayName}: ${it.message}")
                        }
                }
            }
            .addOnFailureListener { log("event ${msg.id} node lookup failed: ${it.message}") }
    }

    private fun sendCheckIn() {
        val nowMs = System.currentTimeMillis()
        val msg = CheckInMessage(
            measuredAt = Instant.now().toString(),
            battery = battery(),
            worn = worn,
            lastPulse = if (lastHeartRate > 0) lastHeartRate else null,
            restingPulse = restingBaseline.measured(nowMs),
            stepsToday = stepsToday(),
            minutesWithoutSteps = minutesWithoutSteps(nowMs)
        )
        Wearable.getNodeClient(this).connectedNodes
            .addOnSuccessListener { nodes ->
                if (nodes.isEmpty()) {
                    log("check-in skipped: no connected nodes")
                    return@addOnSuccessListener
                }
                nodes.forEach { node ->
                    Wearable.getMessageClient(this)
                        .sendMessage(node.id, DataLayer.CHECK_IN, msg.toBytes())
                        .addOnSuccessListener { log("check-in sent to ${node.displayName}") }
                        .addOnFailureListener {
                            log("check-in failed to ${node.displayName}: ${it.message}")
                        }
                }
            }
            .addOnFailureListener { log("check-in node lookup failed: ${it.message}") }
    }

    // Logcat rolls over within an hour or two, and reading it live would keep Wi-Fi on and skew the battery.
    // So every line also goes to a file: `adb shell run-as ro.echocare cat files/monitor.log`
    private fun log(message: String) {
        Log.i(TAG, message)
        File(
            filesDir,
            LOG_FILE
        ).appendText("${LocalTime.now().truncatedTo(ChronoUnit.SECONDS)} $message\n")
    }

    private fun battery() = getSystemService(
        BatteryManager::class.java
    ).getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)

    private fun notification(): Notification {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                getString(R.string.monitoring_channel),
                NotificationManager.IMPORTANCE_LOW
            )
        )
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.monitoring_running))
            .setSmallIcon(R.drawable.splash_icon)
            .setOngoing(true)
            .setContentIntent(open)
            .build()
    }

    private fun fallNotification(): Notification {
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(
                FALL_CHANNEL_ID,
                getString(R.string.fall_channel),
                NotificationManager.IMPORTANCE_HIGH
            )
        )
        val open = PendingIntent.getActivity(
            this,
            1,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return Notification.Builder(this, FALL_CHANNEL_ID)
            .setContentTitle(getString(R.string.are_you_ok_title))
            .setContentText(getString(R.string.app_name))
            .setSmallIcon(R.drawable.splash_icon)
            .setCategory(Notification.CATEGORY_ALARM)
            .setFullScreenIntent(open, true)
            .setAutoCancel(true)
            .build()
    }

    companion object {
        private const val TAG = "SentinelaMonitor"
        private const val CHANNEL_ID = "monitoring"
        private const val FALL_CHANNEL_ID = "fall"
        private const val NOTIFICATION_ID = 1
        private const val FALL_NOTIFICATION_ID = 2
        private const val MINUTE_MS = 60_000L

        // How often the Handler checks for a due minute while the CPU is awake
        private const val TICK_CHECK_MS = 10_000L

        // A batch waits at most this long; a fall still needs 7 s of stillness before it counts (S13)
        private const val BATCH_LATENCY_US = 10_000_000

        // 06 §3's check-in interval; under the 90 s and 45 min silence limits
        private val CHECK_IN_MINUTES = if (BuildConfig.DEMO) 1 else 15
        private const val LOG_FILE = "monitor.log"

        // How long after the last step the wearer is still considered to be moving (UC-09 "not moving")
        private const val MOVING_WINDOW_MS = 30_000L

        // A cap, so a forgotten test does not keep the CPU awake for days
        private const val MAX_WAKE_MS = 4 * 60 * 60_000L

        val running = MutableStateFlow(false)

        // MainActivity observes this; non-null brings up the „Sunteți bine?" screen
        val fallPrompt = MutableStateFlow<FallPrompt?>(null)

        data class FallPrompt(
            val id: String,
            val measuredAt: String,
            val type: String = "fall",
            val snapshot: EventSnapshot = EventSnapshot.EMPTY
        )

        fun start(context: Context) {
            context.startForegroundService(Intent(context, MonitoringService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, MonitoringService::class.java))
        }

        /** Dismiss the fall notification; the activity calls this when the user answers the prompt. */
        fun dismissFallNotification(context: Context) {
            context.getSystemService(NotificationManager::class.java)
                .cancel(FALL_NOTIFICATION_ID)
        }

        /**
         * Hand-raises a synthetic event with a fake snapshot, so the demo can show the whole UC-09
         * loop without waiting for a real anomaly (debug builds only). The intent fires through
         * the service so the full-screen prompt wakes the watch just like a real one.
         */
        fun forceAnomaly(context: Context, type: String) {
            context.startService(
                Intent(context, MonitoringService::class.java)
                    .setAction(ACTION_FORCE_ANOMALY)
                    .putExtra(EXTRA_FORCE_TYPE, type)
            )
        }

        const val ACTION_FORCE_ANOMALY = "ro.echocare.wear.FORCE_ANOMALY"
        const val EXTRA_FORCE_TYPE = "type"
        const val ACTION_SEND_EVENT = "ro.echocare.wear.SEND_EVENT"
        const val EXTRA_EVENT_BYTES = "event_bytes"

        /** The UI calls this to enqueue and send an event; the service handles retries. */
        fun sendEvent(context: Context, msg: ro.echocare.shared.EventMessage) {
            context.startService(
                Intent(context, MonitoringService::class.java)
                    .setAction(ACTION_SEND_EVENT)
                    .putExtra(EXTRA_EVENT_BYTES, msg.toBytes())
            )
        }
    }
}
