package bia.sentinela.wear.presentation

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.health.connect.HealthPermissions
import android.os.SystemClock
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.EdgeButton
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import bia.sentinela.shared.FallDetector
import bia.sentinela.wear.R
import java.util.Locale
import kotlin.math.abs
import kotlinx.coroutines.delay

// Spikes S5 and S13 (06 §6): what the watch's sensors deliver, and how often, while this screen is open.
// Background delivery is a separate test.

private val PERMISSIONS =
    arrayOf(HealthPermissions.READ_HEART_RATE, Manifest.permission.ACTIVITY_RECOGNITION)

// 50 readings a second, the rate fall detection needs (P19)
private const val ACCELEROMETER_PERIOD_US = 20_000

// Per-trial measurements for tuning fall detection (P19). The detector's own thresholds go to :shared.
private const val FREE_FALL_G = 0.4f

// Only a peak above this starts timing the stillness after it, so standing still from the start does not count
private const val IMPACT_G = 1.5f
private const val STILL_TOLERANCE_G = 0.1f
private const val TRIAL_LOG_TAG = "SentinelaTrial"

private fun Context.hasPermissions() = PERMISSIONS.all {
    checkSelfPermission(it) ==
        PackageManager.PERMISSION_GRANTED
}

private class Readings {
    var heartRate by mutableIntStateOf(0)
    var heartRateAccuracy by mutableIntStateOf(SensorManager.SENSOR_STATUS_UNRELIABLE)
    var heartRateAtMs by mutableLongStateOf(0L)
    var steps by mutableIntStateOf(0)
    var accelerationG by mutableFloatStateOf(0f)
    var minG by mutableFloatStateOf(Float.MAX_VALUE)
    var maxG by mutableFloatStateOf(0f)
    var samplesPerSecond by mutableFloatStateOf(0f)
    var rangeG by mutableFloatStateOf(0f)
    var trial by mutableIntStateOf(1)
    var freeFallMs by mutableIntStateOf(0)
    var stillAfterPeakS by mutableFloatStateOf(0f)
    var fallsDetected by mutableIntStateOf(0)

    private var firstStepCount = -1f
    private var windowStartNs = 0L
    private var windowSamples = 0
    private var shownAtNs = 0L

    private var trialStartMs = SystemClock.elapsedRealtime()
    private var stepsAtTrialStart = 0
    private var heartRateAtTrialStart = 0
    private var freeFallStartNs = -1L
    private var longestFreeFallNs = 0L
    private var afterPeak = false
    private var stillStartNs = -1L
    private var longestStillNs = 0L
    private var fallsAtTrialStart = 0
    private val fallDetector = FallDetector()

    // Logs the trial that just ended, for `adb logcat -s SentinelaTrial`, then starts the next one
    fun nextTrial() {
        Log.i(
            TRIAL_LOG_TAG,
            String.format(
                Locale.ROOT,
                "trial=%d seconds=%d minG=%.2f maxG=%.2f freeFallMs=%d stillAfterPeakS=%.1f steps=%d heartRate=%d->%d fallsDetected=%d",
                trial,
                (SystemClock.elapsedRealtime() - trialStartMs) / 1_000,
                minG,
                maxG,
                longestFreeFallNs / 1_000_000,
                longestStillNs / 1e9f,
                steps - stepsAtTrialStart,
                heartRateAtTrialStart,
                heartRate,
                fallsDetected - fallsAtTrialStart
            )
        )
        trial++
        minG = Float.MAX_VALUE
        maxG = 0f
        freeFallMs = 0
        stillAfterPeakS = 0f
        trialStartMs = SystemClock.elapsedRealtime()
        stepsAtTrialStart = steps
        heartRateAtTrialStart = heartRate
        fallsAtTrialStart = fallsDetected
        freeFallStartNs = -1L
        longestFreeFallNs = 0L
        afterPeak = false
        stillStartNs = -1L
        longestStillNs = 0L
    }

    val listener = object : SensorEventListener {
        override fun onSensorChanged(event: SensorEvent) {
            when (event.sensor.type) {
                Sensor.TYPE_HEART_RATE -> onHeartRate(event)
                Sensor.TYPE_STEP_COUNTER -> onSteps(event)
                Sensor.TYPE_ACCELEROMETER -> onAcceleration(event)
            }
        }

        override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {
            if (sensor.type == Sensor.TYPE_HEART_RATE) heartRateAccuracy = accuracy
        }
    }

    private fun onHeartRate(event: SensorEvent) {
        heartRateAccuracy = event.accuracy
        // Samsung reports 0 while it is still acquiring a pulse
        val bpm = event.values[0].toInt()
        if (bpm > 0) {
            heartRate = bpm
            heartRateAtMs = SystemClock.elapsedRealtime()
        }
    }

    private fun onSteps(event: SensorEvent) {
        // The counter is cumulative since boot; show the steps since this screen opened
        if (firstStepCount < 0) firstStepCount = event.values[0]
        steps = (event.values[0] - firstStepCount).toInt()
    }

    private fun onAcceleration(event: SensorEvent) {
        val (x, y, z) = event.values
        val g = FallDetector.accelerationG(x, y, z)
        if (fallDetector.onReading(event.timestamp / 1_000_000, g)) {
            fallsDetected++
            Log.i(TRIAL_LOG_TAG, "fall detected in trial=$trial")
        }
        // Extremes from every reading, so a short impact is never missed
        if (g < minG) minG = g
        if (g > maxG) maxG = g

        val t = event.timestamp
        // The longest stretch below the free-fall threshold: walking also dips below it, but only briefly
        if (g < FREE_FALL_G) {
            if (freeFallStartNs < 0) freeFallStartNs = t
            longestFreeFallNs = maxOf(longestFreeFallNs, t - freeFallStartNs)
        } else {
            freeFallStartNs = -1L
        }
        // The longest stillness after the strongest peak; a higher peak starts it over
        if (g > IMPACT_G && g >= maxG) {
            afterPeak = true
            stillStartNs = -1L
            longestStillNs = 0L
        }
        if (afterPeak && abs(g - 1f) < STILL_TOLERANCE_G) {
            if (stillStartNs < 0) stillStartNs = t
            longestStillNs = maxOf(longestStillNs, t - stillStartNs)
        } else {
            stillStartNs = -1L
        }

        if (windowStartNs == 0L) windowStartNs = event.timestamp
        windowSamples++
        val windowNs = event.timestamp - windowStartNs
        if (windowNs >= 1_000_000_000L) {
            samplesPerSecond = windowSamples * 1e9f / windowNs
            windowStartNs = event.timestamp
            windowSamples = 0
        }
        // The current value at most ten times a second, to spare recomposition
        if (event.timestamp - shownAtNs >= 100_000_000L) {
            accelerationG = g
            freeFallMs = (longestFreeFallNs / 1_000_000).toInt()
            stillAfterPeakS = longestStillNs / 1e9f
            shownAtNs = event.timestamp
        }
    }
}

@Composable
private fun rememberReadings(permissionsGranted: Boolean): Readings {
    val context = LocalContext.current
    val readings = remember { Readings() }
    DisposableEffect(permissionsGranted) {
        val sensorManager = context.getSystemService(SensorManager::class.java)
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            readings.rangeG = it.maximumRange / SensorManager.GRAVITY_EARTH
            sensorManager.registerListener(readings.listener, it, ACCELEROMETER_PERIOD_US)
        }
        // Pulse and steps need the runtime permissions; registering without them fails
        if (permissionsGranted) {
            listOf(Sensor.TYPE_HEART_RATE, Sensor.TYPE_STEP_COUNTER)
                .mapNotNull(sensorManager::getDefaultSensor)
                .forEach {
                    sensorManager.registerListener(
                        readings.listener,
                        it,
                        SensorManager.SENSOR_DELAY_NORMAL
                    )
                }
        }
        onDispose { sensorManager.unregisterListener(readings.listener) }
    }
    return readings
}

@Composable
fun SensorTestScreen() {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(context.hasPermissions()) }
    val request =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
            granted = context.hasPermissions()
        }
    LaunchedEffect(Unit) {
        if (!granted) request.launch(PERMISSIONS)
    }
    val readings = rememberReadings(granted)
    // Ticks every second, so the age of the last pulse keeps counting between readings
    val nowMs by produceState(SystemClock.elapsedRealtime()) {
        while (true) {
            delay(1_000)
            value = SystemClock.elapsedRealtime()
        }
    }

    val listState = rememberTransformingLazyColumnState()
    ScreenScaffold(
        scrollState = listState,
        edgeButton = {
            EdgeButton(onClick = readings::nextTrial) {
                Text(stringResource(R.string.next_trial))
            }
        }
    ) { contentPadding ->
        TransformingLazyColumn(contentPadding = contentPadding, state = listState) {
            item {
                ListHeader { Text(stringResource(R.string.trial_title, readings.trial)) }
            }
            if (!granted) {
                item { Line(stringResource(R.string.permission_needed)) }
                item {
                    Button(onClick = {
                        request.launch(PERMISSIONS)
                    }, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.grant_permission))
                    }
                }
            }
            item {
                Line(
                    when {
                        readings.heartRateAccuracy == SensorManager.SENSOR_STATUS_NO_CONTACT ->
                            stringResource(R.string.heart_rate_no_contact)
                        readings.heartRate == 0 -> stringResource(R.string.heart_rate_waiting)
                        else -> stringResource(R.string.heart_rate, readings.heartRate)
                    }
                )
            }
            if (readings.heartRateAtMs > 0) {
                item {
                    Line(
                        stringResource(
                            R.string.heart_rate_age,
                            (nowMs - readings.heartRateAtMs) / 1_000
                        )
                    )
                }
            }
            item { Line(stringResource(R.string.steps, readings.steps)) }
            item { Line(stringResource(R.string.acceleration, readings.accelerationG)) }
            if (readings.maxG > 0f) {
                item {
                    Line(
                        stringResource(R.string.acceleration_min_max, readings.minG, readings.maxG)
                    )
                }
            }
            item { Line(stringResource(R.string.free_fall, readings.freeFallMs)) }
            item { Line(stringResource(R.string.still_after_peak, readings.stillAfterPeakS)) }
            item { Line(stringResource(R.string.falls_detected, readings.fallsDetected)) }
            item {
                Line(
                    stringResource(R.string.sample_rate, readings.samplesPerSecond, readings.rangeG)
                )
            }
        }
    }
}

@Composable
private fun Line(text: String) {
    Text(text, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
}
