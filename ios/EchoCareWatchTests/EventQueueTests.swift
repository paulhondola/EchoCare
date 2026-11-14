import Foundation
import Shared
import Testing

@testable import EchoCareWatch

// 04 §3: the watch keeps events and resends them until the phone acks. Ported from android's
// EventQueueTest.kt, plus the two cases the iOS plan adds (Review Focus 1).
struct EventQueueTests {
    private func newDirectory() -> URL {
        FileManager.default.temporaryDirectory
            .appending(path: "echocare-queue-\(UUID().uuidString)", directoryHint: .isDirectory)
    }

    @Test func anEnqueuedEventIsPendingUntilItIsAcked() {
        let q = EventQueue(directory: newDirectory())
        let msg = EventMessage(id: "1", type: "fall", measuredAt: "t")
        q.enqueue(msg)
        #expect(q.pending() == [msg])
        q.ack(id: "1")
        #expect(q.pending() == [])
    }

    @Test func queueSurvivesRestart() {
        let dir = newDirectory()
        let msg = EventMessage(
            id: "a", type: "high_pulse_at_rest", measuredAt: "t",
            snapshot: EventSnapshot(
                pulse: 125, restingBaseline: 66, moving: false, minutesWithoutSteps: 0, battery: 80))
        EventQueue(directory: dir).enqueue(msg)
        #expect(EventQueue(directory: dir).pending() == [msg])
    }

    @Test func ackRemovesOnlyThatId() {
        let q = EventQueue(directory: newDirectory())
        let a = EventMessage(id: "a", type: "fall", measuredAt: "t1")
        let b = EventMessage(id: "b", type: "inactivity", measuredAt: "t2")
        q.enqueue(a)
        q.enqueue(b)
        q.ack(id: "a")
        #expect(q.pending() == [b])
    }

    @Test func enqueueingTheSameIdTwiceKeepsOne() {
        let q = EventQueue(directory: newDirectory())
        let msg = EventMessage(id: "a", type: "fall", measuredAt: "t")
        q.enqueue(msg)
        q.enqueue(msg)
        #expect(q.pending() == [msg])
    }

    @Test func anUnreadableFileIsSkipped() throws {
        let dir = newDirectory()
        let q = EventQueue(directory: dir)
        try Data("not json".utf8).write(to: dir.appending(path: "broken.json"))
        let msg = EventMessage(id: "a", type: "fall", measuredAt: "t")
        q.enqueue(msg)
        #expect(q.pending() == [msg])
    }

    @Test func anAckForAPathOutsideTheQueueTouchesNothing() throws {
        let parent = newDirectory()
        let dir = parent.appending(path: "events", directoryHint: .isDirectory)
        let q = EventQueue(directory: dir)
        let outside = parent.appending(path: "keep.json")
        try Data("{}".utf8).write(to: outside)
        q.ack(id: "../keep")
        q.ack(id: "")
        #expect(FileManager.default.fileExists(atPath: outside.path()))
    }
}
