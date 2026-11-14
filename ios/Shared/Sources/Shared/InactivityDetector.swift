/// No steps for long enough during an active warning (UC-09 step 1, event type `inactivity`). The
/// spec limit is 4 h normally, 60 s in a demo (06 §3). The caller feeds every step reading and
/// polls `isInactive(nowMs:)` on a timer; it fires once per gap and the caller clears it with
/// `reset()` when it has acted.
public final class InactivityDetector {
    private let limitMs: Int64
    private var lastStepAtMs: Int64 = -1
    private var fired = false

    public init(limitMs: Int64 = 14_400_000) {
        self.limitMs = limitMs
    }

    public func onStep(atMs: Int64) {
        lastStepAtMs = atMs
        fired = false
    }

    /// True once when the gap has first exceeded `limitMs`.
    public func isInactive(nowMs: Int64) -> Bool {
        if fired || lastStepAtMs < 0 { return false }
        if nowMs - lastStepAtMs < limitMs { return false }
        fired = true
        return true
    }

    public func reset() {
        fired = false
        lastStepAtMs = -1
    }
}
