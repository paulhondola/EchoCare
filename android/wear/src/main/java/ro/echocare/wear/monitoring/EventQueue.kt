package ro.echocare.wear.monitoring

import java.io.File
import ro.echocare.shared.EventMessage

/**
 * Pending events to resend until the phone acks them (04 §3: "the watch keeps events and resends
 * them"). One file per event, named after its id, containing the serialised [EventMessage]. Caller
 * is expected to re-send [pending] on every minute tick and after a connection comes back; the
 * phone replies on `/echocare/received/<id>` which clears the file.
 */
class EventQueue(dir: File) {
    private val folder: File = dir.apply { mkdirs() }

    fun enqueue(msg: EventMessage) {
        File(folder, msg.id).writeBytes(msg.toBytes())
    }

    fun ack(id: String) {
        File(folder, id).delete()
    }

    fun pending(): List<EventMessage> = folder.listFiles()?.mapNotNull { file ->
        runCatching { EventMessage.fromBytes(file.readBytes()) }.getOrNull()
    } ?: emptyList()
}
