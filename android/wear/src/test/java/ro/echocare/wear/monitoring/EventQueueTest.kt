package ro.echocare.wear.monitoring

import java.nio.file.Files
import org.junit.Assert.assertEquals
import org.junit.Test
import ro.echocare.shared.EventMessage

class EventQueueTest {
    private fun newQueue() = EventQueue(Files.createTempDirectory("echocare-queue").toFile())

    @Test
    fun `an enqueued event is pending until it is acked`() {
        val q = newQueue()
        val msg = EventMessage(id = "1", type = "fall", measuredAt = "t")
        q.enqueue(msg)
        assertEquals(listOf(msg), q.pending())
        q.ack("1")
        assertEquals(emptyList<EventMessage>(), q.pending())
    }

    @Test
    fun `pending survives a new queue instance on the same folder`() {
        val dir = Files.createTempDirectory("echocare-queue").toFile()
        EventQueue(dir).enqueue(EventMessage(id = "a", type = "fall", measuredAt = "t"))
        assertEquals(1, EventQueue(dir).pending().size)
    }
}
