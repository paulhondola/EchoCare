import Testing

@testable import EchoCare

// The medic home's to-do list (design 2026-11-13 medic home): which rows are tasks, in what order.
// Ported from Android's home/TasksTest.kt.
struct TasksTests {
    private func row(
        _ id: String, _ state: String, medical: String? = nil, createdAt: String? = nil,
        acceptedAt: String? = nil
    ) -> SeniorRow {
        SeniorRow(
            id: id, fullName: id, formOfAddress: "Dna", phone: "+40700000000", landline: false, state: state,
            createdAt: createdAt, acceptedAt: acceptedAt, medicalRecordState: medical)
    }

    @Test func ordersByImportance() {
        let rows = [
            row("d", "draft"),
            row("u", "unreachable"),
            row("w", "wrong_number"),
            row("f", "active", medical: "failed"),
            row("c", "active", medical: "review"),
        ]
        #expect(tasksOf(rows).map(\.row.id) == ["c", "f", "w", "u", "d"])
    }

    @Test func oneTaskPerSeniorTheMostImportant() {
        let tasks = tasksOf([row("a", "wrong_number", medical: "review")])
        #expect(tasks == [MedicTask(row: tasks[0].row, kind: .confirm)])
    }

    @Test func noTaskForUnknownOrSettledValues() {
        let rows = [
            row("x", "active", medical: "archived"),
            row("y", "withdrawn", medical: "review"),
            row("z", "refused", medical: "failed"),
            row("q", "someday", medical: "review"),
            row("g", "active", medical: "confirmed"),
            row("p", "accepted", medical: "pending"),
            row("s", "submitted"),
        ]
        #expect(tasksOf(rows).isEmpty)
    }

    @Test func oldestFirstWithinAKindNullTimesLast() {
        let rows = [
            row("new", "draft", createdAt: "2026-11-12T10:00:00Z"),
            row("none", "draft"),
            row("old", "draft", createdAt: "2026-11-10T10:00:00Z"),
        ]
        #expect(tasksOf(rows).map(\.row.id) == ["old", "new", "none"])
    }

    @Test func welcomeCallProblemsOldestAcceptedFirst() {
        let rows = [
            row("late", "unreachable", acceptedAt: "2026-11-12T10:00:00Z"),
            row("early", "unreachable", acceptedAt: "2026-11-09T10:00:00Z"),
        ]
        #expect(tasksOf(rows).map(\.row.id) == ["early", "late"])
    }
}
