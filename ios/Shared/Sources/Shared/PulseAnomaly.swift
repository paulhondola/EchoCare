/// High pulse at rest (UC-09 step 1, event type `high_pulse_at_rest`). A reading is anomalous when
/// the wearer is not moving and the pulse exceeds the resting baseline by at least `marginBpm`.
/// The spec doesn't fix a multiplier (Q, open); this uses a flat margin and holds for `holdMs` so
/// one spurious spike doesn't start a call.
public final class PulseAnomaly {
    private let marginBpm: Int
    private let holdMs: Int64
    private var sinceMs: Int64 = -1

    public init(marginBpm: Int = 25, holdMs: Int64 = 60_000) {
        self.marginBpm = marginBpm
        self.holdMs = holdMs
    }

    /// Feed every valid heart-rate reading with the wearer's current resting baseline. Returns
    /// true the first time the pulse has stayed high at rest for at least `holdMs`; the caller
    /// then clears the detector with `reset()` once it has acted on the anomaly. A nil baseline (not
    /// measured yet) is never an anomaly: a default would call a senior whose normal pulse is high
    /// within a minute of putting the watch on.
    public func onReading(atMs: Int64, bpm: Int, baselineBpm: Int?, moving: Bool) -> Bool {
        let high = baselineBpm.map { !moving && bpm > 0 && bpm >= $0 + marginBpm } ?? false
        if !high {
            sinceMs = -1
            return false
        }
        if sinceMs < 0 { sinceMs = atMs }
        return atMs - sinceMs >= holdMs
    }

    public func reset() {
        sinceMs = -1
    }
}
