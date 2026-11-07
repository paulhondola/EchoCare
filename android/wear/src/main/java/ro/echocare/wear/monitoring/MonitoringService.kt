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
import ro.echocare.shared.FallDetector
import ro.echocare.wear.R
import ro.echocare.wear.presentation.MainActivity
import java.io.File
import java.time.LocalTime
import java.time.temporal.ChronoUnit
import kotlinx.coroutines.flow.MutableStateFlow

// 50 readings a second, the rate fall detection needs (P19)
internal const val ACCELEROMETER_PERIOD_US = 20_000

/**
 * Spike S5 (06 §6): does the watch keep delivering pulse, steps and the accelerometer with the
 * screen off, and what does it cost in battery? Runs the fall detector the whole time and logs a
 * summary every minute, for `adb logcat -s SentinelaMonitor`.
 */
class MonitoringService :
    Service(),
    SensorEventListener {
    private lateinit var sensorManager: SensorManager
    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler
    private lateinit var wakeLock: PowerManager.WakeLock
    private val fallDetector = FallDetector()

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

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIFICATION_ID, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH)
        // Keeps the CPU awake with the screen off, so no reading is lost while it sleeps. S5 measures what that costs
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "EchoCare:monitoring")
            .apply { acquire(MAX_WAKE_MS) }
        thread = HandlerThread(TAG).apply { start() }
        handler = Handler(thread.looper)
        sensorManager = getSystemService(SensorManager::class.java)
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            sensorManager.registerListener(this, it, ACCELEROMETER_PERIOD_US, handler)
        }
        listOf(Sensor.TYPE_HEART_RATE, Sensor.TYPE_STEP_COUNTER)
            .mapNotNull(sensorManager::getDefaultSensor)
            .forEach {
                sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL, handler)
            }
        handler.postDelayed(::logMinute, MINUTE_MS)
        running.value = true
        // One session per file, so it never grows past a few kilobytes an hour
        File(filesDir, LOG_FILE).delete()
        log("started battery=${battery()}%")
    }

    override fun onDestroy() {
        sensorManager.unregisterListener(this)
        handler.removeCallbacksAndMessages(null)
        thread.quitSafely()
        if (wakeLock.isHeld) wakeLock.release()
        running.value = false
        log("stopped after minute=$minute battery=${battery()}%")
        super.onDestroy()
    }

    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> onAcceleration(event)
            Sensor.TYPE_HEART_RATE -> {
                // Samsung reports 0 while it is still acquiring a pulse
                val bpm = event.values[0].toInt()
                if (bpm > 0) {
                    heartRateReadings++
                    lastHeartRate = bpm
                }
            }
            Sensor.TYPE_STEP_COUNTER -> {
                if (stepsAtMinuteStart < 0) stepsAtMinuteStart = event.values[0]
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
            log("fall detected in minute=${minute + 1}")
            // Tells the wearer, with the screen off, that the fall was caught. The „Sunteți bine?" prompt comes later
            getSystemService(VibratorManager::class.java).defaultVibrator
                .vibrate(VibrationEffect.createOneShot(600, VibrationEffect.DEFAULT_AMPLITUDE))
        }
    }

    private fun logMinute() {
        minute++
        val steps = if (stepsAtMinuteStart < 0) 0 else (lastStepCount - stepsAtMinuteStart).toInt()
        log(
            "minute=$minute accel=$accelReadings maxGapMs=${maxAccelGapNs / 1_000_000} " +
                "heartRates=$heartRateReadings lastHeartRate=$lastHeartRate steps=$steps falls=$falls battery=${battery()}%"
        )
        accelReadings = 0
        maxAccelGapNs = 0L
        heartRateReadings = 0
        stepsAtMinuteStart = lastStepCount
        falls = 0
        handler.postDelayed(::logMinute, MINUTE_MS)
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

    companion object {
        private const val TAG = "SentinelaMonitor"
        private const val CHANNEL_ID = "monitoring"
        private const val NOTIFICATION_ID = 1
        private const val MINUTE_MS = 60_000L
        private const val LOG_FILE = "monitor.log"

        // A cap, so a forgotten test does not keep the CPU awake for days
        private const val MAX_WAKE_MS = 4 * 60 * 60_000L

        val running = MutableStateFlow(false)

        fun start(context: Context) {
            context.startForegroundService(Intent(context, MonitoringService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, MonitoringService::class.java))
        }
    }
}
