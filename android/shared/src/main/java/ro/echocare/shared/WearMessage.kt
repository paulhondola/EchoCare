package ro.echocare.shared

/** Wire types for the watch → phone Data Layer messages (04 §3, UC-09, UC-13). */

data class CheckInMessage(
    val measuredAt: String,
    val battery: Int?,
    val worn: Boolean,
    val lastPulse: Int?,
    // Added by ADR-006; an older watch leaves them out, an older phone ignores them
    val restingPulse: Int? = null,
    val stepsToday: Int? = null,
    val minutesWithoutSteps: Int? = null
) {
    fun toBytes(): ByteArray = buildString {
        append("{\"measured_at\":\"$measuredAt\"")
        battery?.let { append(",\"battery\":$it") }
        append(",\"worn\":$worn")
        lastPulse?.let { append(",\"last_pulse\":$it") }
        restingPulse?.let { append(",\"resting_pulse\":$it") }
        stepsToday?.let { append(",\"steps_today\":$it") }
        minutesWithoutSteps?.let { append(",\"minutes_without_steps\":$it") }
        append("}")
    }.encodeToByteArray()

    companion object {
        fun fromBytes(bytes: ByteArray): CheckInMessage {
            val json = bytes.decodeToString()
            return CheckInMessage(
                measuredAt = json.jsonString("measured_at") ?: "",
                battery = json.jsonInt("battery"),
                worn = json.jsonBoolean("worn") ?: true,
                lastPulse = json.jsonInt("last_pulse"),
                restingPulse = json.jsonInt("resting_pulse"),
                stepsToday = json.jsonInt("steps_today"),
                minutesWithoutSteps = json.jsonInt("minutes_without_steps")
            )
        }
    }
}

data class EventSnapshot(
    val pulse: Int?,
    val restingBaseline: Int?,
    val moving: Boolean?,
    val minutesWithoutSteps: Int?,
    val battery: Int?
) {
    companion object {
        val EMPTY = EventSnapshot(null, null, null, null, null)
    }
}

data class EventMessage(
    val id: String,
    val type: String,
    val measuredAt: String,
    val snapshot: EventSnapshot = EventSnapshot.EMPTY
) {
    fun toBytes(): ByteArray = buildString {
        append("{\"id\":\"$id\",\"type\":\"$type\",\"measured_at\":\"$measuredAt\"")
        val s = snapshot
        if (s != EventSnapshot.EMPTY) {
            append(",\"snapshot\":{")
            val parts = mutableListOf<String>()
            s.pulse?.let { parts += "\"pulse\":$it" }
            s.restingBaseline?.let { parts += "\"resting_baseline\":$it" }
            s.moving?.let { parts += "\"moving\":$it" }
            s.minutesWithoutSteps?.let { parts += "\"minutes_without_steps\":$it" }
            s.battery?.let { parts += "\"battery\":$it" }
            append(parts.joinToString(","))
            append("}")
        }
        append("}")
    }.encodeToByteArray()

    companion object {
        fun fromBytes(bytes: ByteArray): EventMessage {
            val json = bytes.decodeToString()
            return EventMessage(
                id = json.jsonString("id") ?: "",
                type = json.jsonString("type") ?: "fall",
                measuredAt = json.jsonString("measured_at") ?: "",
                snapshot = EventSnapshot(
                    pulse = json.jsonInt("pulse"),
                    restingBaseline = json.jsonInt("resting_baseline"),
                    moving = json.jsonBoolean("moving"),
                    minutesWithoutSteps = json.jsonInt("minutes_without_steps"),
                    battery = json.jsonInt("battery")
                )
            )
        }
    }
}

// shortcut: matches only simple string values with no escaped quotes; wire format never has them
private fun String.jsonString(key: String): String? =
    Regex(""""$key":"([^"]*)"?""").find(this)?.groupValues?.get(1)

private fun String.jsonInt(key: String): Int? =
    Regex(""""$key":(\d+)""").find(this)?.groupValues?.get(1)?.toIntOrNull()

private fun String.jsonBoolean(key: String): Boolean? =
    Regex(""""$key":(true|false)""").find(this)?.groupValues?.get(1)
        ?.let { it == "true" }
