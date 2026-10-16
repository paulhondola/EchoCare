package ro.echocare.ui

/**
 * A Romanian E.164 number as people read it: "0722 111 222", "021 456 7788". Any other number
 * stays as it is. The dashboard's formatPhone does the same (dashboard/src/utils/phone.ts).
 */
fun formatPhone(e164: String): String {
    val rest = Regex("^\\+40(\\d{9})$").find(e164)?.groupValues?.get(1) ?: return e164
    val n = "0$rest"
    // Bucharest landlines have a three-digit prefix (021, 031); the rest four (0722, 0264)
    return if (Regex("^0[23]1").containsMatchIn(n)) {
        "${n.take(3)} ${n.substring(3, 6)} ${n.substring(6)}"
    } else {
        "${n.take(4)} ${n.substring(4, 7)} ${n.substring(7)}"
    }
}
