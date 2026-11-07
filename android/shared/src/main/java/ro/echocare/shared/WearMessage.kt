package ro.echocare.shared

/** Wire types for the watch → phone Data Layer messages (04 §3, UC-09, UC-13). */

data class CheckInMessage(
    val measuredAt: String,
    val battery: Int?,
    val worn: Boolean,
    val lastPulse: Int?
) {
    fun toBytes(): ByteArray = buildString {
        append("{\"measured_at\":\"$measuredAt\"")
        battery?.let { append(",\"battery\":$it") }
        append(",\"worn\":$worn")
        lastPulse?.let { append(",\"last_pulse\":$it") }
        append("}")
    }.encodeToByteArray()

    companion object {
        fun fromBytes(bytes: ByteArray): CheckInMessage {
            val json = bytes.decodeToString()
            return CheckInMessage(
                measuredAt = json.jsonString("measured_at") ?: "",
                battery = json.jsonInt("battery"),
                worn = json.jsonBoolean("worn") ?: true,
                lastPulse = json.jsonInt("last_pulse")
            )
        }
    }
}

data class EventMessage(
    val id: String,
    val type: String,
    val measuredAt: String
) {
    fun toBytes(): ByteArray =
        """{"id":"$id","type":"$type","measured_at":"$measuredAt"}""".encodeToByteArray()

    companion object {
        fun fromBytes(bytes: ByteArray): EventMessage {
            val json = bytes.decodeToString()
            return EventMessage(
                id = json.jsonString("id") ?: "",
                type = json.jsonString("type") ?: "fall",
                measuredAt = json.jsonString("measured_at") ?: ""
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
