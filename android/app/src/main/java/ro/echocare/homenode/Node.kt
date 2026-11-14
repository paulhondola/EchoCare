package ro.echocare.homenode

import java.time.Instant
import java.util.UUID
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import ro.echocare.EventForm
import ro.echocare.EventSnapshotForm
import ro.echocare.RoomReadingForm

/**
 * The home node's GATT service (04 §3, 08-ecou.md §3.1): its UUIDs, the JSON texts it sends,
 * and what the phone makes of them for FastAPI. Pure, so it is tested on the JVM.
 *
 * The node's clock is not set: it reports ages in seconds, and the phone turns them into times
 * measured with its own clock before forwarding (04 §3).
 */
object NodeUuids {
    private fun of(n: Int) = UUID.fromString("ec0f%04x-7765-4f56-abaf-af4938f246ad".format(n))

    val SERVICE: UUID = of(0x0000)
    val ROOM_READING: UUID = of(0x0001)
    val MOTION: UUID = of(0x0002)
    val SOS_PRESS: UUID = of(0x0003)
    val ACKNOWLEDGE: UUID = of(0x0004)
    val LIGHT: UUID = of(0x0005)
    val FALL: UUID = of(0x0006)
    val ROOM_STATE: UUID = of(0x0007)

    /** The standard descriptor that turns notifications on. */
    val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    val NOTIFIED = listOf(ROOM_READING, MOTION, SOS_PRESS, FALL)
}

private val json = Json { ignoreUnknownKeys = true }

@Serializable
data class NodeReading(
    val temperature: Double,
    val humidity: Double? = null,
    @SerialName("seconds_since_motion") val secondsSinceMotion: Long? = null,
    @SerialName("seconds_since_start") val secondsSinceStart: Long? = null,
    @SerialName("forecast_60m") val forecast60m: Double? = null
)

@Serializable
data class NodeSos(
    val id: String,
    @SerialName("seconds_ago") val secondsAgo: Long = 0,
    val via: String? = null
)

@Serializable
data class NodeFall(
    val id: String,
    @SerialName("seconds_ago") val secondsAgo: Long = 0,
    @SerialName("seconds_still") val secondsStill: Double? = null,
    @SerialName("object_angle_deg") val objectAngleDeg: Double? = null,
    @SerialName("object_distance_m") val objectDistanceM: Double? = null,
    val scan: List<Double>? = null
)

/** A text the node sent, or null when it is not what that characteristic carries. */
fun parseReading(text: String): NodeReading? = runCatching {
    json.decodeFromString<NodeReading>(text)
}.getOrNull()

fun parseSos(text: String): NodeSos? = runCatching { json.decodeFromString<NodeSos>(text) }
    .getOrNull()

fun parseFall(text: String): NodeFall? = runCatching { json.decodeFromString<NodeFall>(text) }
    .getOrNull()

/** POST /me/room-readings' body, timed by the phone's clock (P21). */
fun NodeReading.toForm(now: Instant): RoomReadingForm = RoomReadingForm(
    measuredAt = now.toString(),
    temperature = temperature,
    humidity = humidity,
    lastMotionAt = secondsSinceMotion?.let { now.minusSeconds(it).toString() },
    forecast60m = forecast60m
)

/**
 * The node's SOS as POST /me/events' body. Like the watch's button, it is a request to be called
 * (`manual_request`); its source makes the call say the home sensor rang it (04 §3, §4.2).
 */
fun NodeSos.toEventForm(
    now: Instant,
    latitude: Double? = null,
    longitude: Double? = null,
    accuracyM: Double? = null
): EventForm = EventForm(
    id = id,
    type = "manual_request",
    measuredAt = now.minusSeconds(secondsAgo).toString(),
    source = SOURCE,
    latitude = latitude,
    longitude = longitude,
    locationAccuracyM = accuracyM
)

/** A fall found by the node's floor search, with the sweep for DAS's map (P24). */
fun NodeFall.toEventForm(
    now: Instant,
    latitude: Double? = null,
    longitude: Double? = null,
    accuracyM: Double? = null
): EventForm = EventForm(
    id = id,
    type = "fall",
    measuredAt = now.minusSeconds(secondsAgo).toString(),
    source = SOURCE,
    snapshot = EventSnapshotForm(
        objectAngleDeg = objectAngleDeg,
        objectDistanceM = objectDistanceM,
        secondsStill = secondsStill,
        scan = scan
    ),
    latitude = latitude,
    longitude = longitude,
    locationAccuracyM = accuracyM
)

/** What the node's light shows (04 §3): `call` while a call rings or is live, else the code. */
fun lightFor(code: String?, callInProgress: Boolean?): String = when {
    callInProgress == true -> "call"
    code in setOf("green", "yellow", "red") -> code!!
    else -> "green"
}

/** „Cutia 3F2A”: the last four characters of the address, printed on the box too (UC-15). */
fun boxLabel(address: String): String = address.replace(":", "").takeLast(4).uppercase()

const val SOURCE = "home_node"
