/// The wearer's resting pulse, tracked as a rolling mean of still-moment readings (UC-09 step 1).
/// Only readings reported while the wearer is not moving contribute, so a run at 150 bpm doesn't
/// push the baseline up. Starts `defaultBpm` until at least `minSamples` still readings land; from
/// then on a reading flags as anomalous when it stays above the baseline by a wide margin while not
/// moving.
public final class RestingBaseline {
    private struct Sample {
        let atMs: Int64
        let bpm: Int
    }

    private let windowMs: Int64
    private let minSamples: Int
    private let defaultBpm: Int
    private var samples: [Sample] = []

    public init(windowMs: Int64 = 3_600_000, minSamples: Int = 10, defaultBpm: Int = 70) {
        self.windowMs = windowMs
        self.minSamples = minSamples
        self.defaultBpm = defaultBpm
    }

    /// Call for every valid heart-rate reading. Non-still readings are ignored.
    public func onReading(atMs: Int64, bpm: Int, moving: Bool) {
        if !moving && bpm > 0 { samples.append(Sample(atMs: atMs, bpm: bpm)) }
        drop(atMs)
    }

    /// The mean of still readings in the window, or `defaultBpm` before enough have landed.
    public func value(nowMs: Int64) -> Int { measured(nowMs: nowMs) ?? defaultBpm }

    /// The mean of still readings in the window, or nil before enough have landed: what the check-in reports (ADR-006).
    public func measured(nowMs: Int64) -> Int? {
        drop(nowMs)
        if samples.count < minSamples { return nil }
        return max(samples.reduce(0) { $0 + $1.bpm } / samples.count, 1)
    }

    private func drop(_ nowMs: Int64) {
        let cutoff = nowMs - windowMs
        // Samples arrive in time order, so the stale ones are a prefix
        let stale = samples.prefix { $0.atMs < cutoff }.count
        if stale > 0 { samples.removeFirst(stale) }
    }
}
