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
import bia.sentinela.wear.R
import kotlin.math.sqrt
import kotlinx.coroutines.delay

// Spikes S5 and S13 (06 §6): what the watch's sensors deliver, and how often, while this screen is open.
// Background delivery is a separate test.

private val PERMISSIONS =
    arrayOf(HealthPermissions.READ_HEART_RATE, Manifest.permission.ACTIVITY_RECOGNITION)

// 50 readings a second, the rate fall detection needs (P19)
private const val ACCELEROMETER_PERIOD_US = 20_000

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

    private var firstStepCount = -1f
    private var windowStartNs = 0L
    private var windowSamples = 0
    private var shownAtNs = 0L

    fun resetExtremes() {
        minG = Float.MAX_VALUE
        maxG = 0f
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
        val g = sqrt(x * x + y * y + z * z) / SensorManager.GRAVITY_EARTH
        // Extremes from every reading, so a short impact is never missed
        if (g < minG) minG = g
        if (g > maxG) maxG = g

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
            EdgeButton(onClick = readings::resetExtremes) {
                Text(stringResource(R.string.reset_min_max))
            }
        }
    ) { contentPadding ->
        TransformingLazyColumn(contentPadding = contentPadding, state = listState) {
            item {
                ListHeader { Text(stringResource(R.string.sensor_test_title)) }
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
