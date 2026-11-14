import HealthKit
import os

/// Sends the watch's Apple Health blood oxygen and ECG readings to FastAPI (04 §3, ADR-008). The
/// watch writes them to Health, Health syncs them to this phone, and an anchored query per type
/// reads the last 24 hours at each start and whatever arrives afterwards. It never asks for
/// access: `WatchLink.startMonitoring` does, with the heart rate. The server drops a reading it
/// already has (the id is the sample's UUID), so every start re-sends the day. A failed post is
/// logged and dropped; the next start sends it again.
@MainActor
final class HealthSync {
    static let shared = HealthSync(api: ApiClient(tokens: FirebaseTokenSource()))

    private let api: ApiClient
    private let store = HKHealthStore()
    private let log = Logger(subsystem: "ro.echocare.ios", category: "health")
    private var running = false
    // Held, or HealthKit stops them when they are deallocated
    private var queries: [HKQuery] = []

    init(api: ApiClient) {
        self.api = api
    }

    /// Starts the two queries; once per launch, and nothing without HealthKit (an iPad).
    func start() {
        guard !running, HKHealthStore.isHealthDataAvailable() else { return }
        running = true
        let day = HKQuery.predicateForSamples(
            withStart: Date().addingTimeInterval(-24 * 3600), end: nil)
        let onOxygen:
            @Sendable (
                HKAnchoredObjectQuery, [HKSample]?, [HKDeletedObject]?, HKQueryAnchor?, (any Error)?
            ) -> Void = { [weak self] _, samples, _, _, error in
                // Off the main actor: copy out Sendable values, then hop
                let readings = (samples as? [HKQuantitySample] ?? []).map {
                    (
                        id: $0.uuid.uuidString, at: $0.startDate,
                        fraction: $0.quantity.doubleValue(for: .percent())
                    )
                }
                let reason = error.map { String(describing: $0) }
                Task { @MainActor in
                    self?.oxygen(readings, error: reason)
                }
            }
        let onEcg:
            @Sendable (
                HKAnchoredObjectQuery, [HKSample]?, [HKDeletedObject]?, HKQueryAnchor?, (any Error)?
            ) -> Void = { [weak self] _, samples, _, _, error in
                let found = samples as? [HKElectrocardiogram] ?? []
                let reason = error.map { String(describing: $0) }
                Task { @MainActor in
                    self?.electrocardiograms(found, error: reason)
                }
            }
        let oxygen = HKAnchoredObjectQuery(
            type: HKQuantityType(.oxygenSaturation), predicate: day, anchor: nil,
            limit: HKObjectQueryNoLimit, resultsHandler: onOxygen)
        let ecg = HKAnchoredObjectQuery(
            type: HKObjectType.electrocardiogramType(), predicate: day, anchor: nil,
            limit: HKObjectQueryNoLimit, resultsHandler: onEcg)
        oxygen.updateHandler = onOxygen
        ecg.updateHandler = onEcg
        queries = [oxygen, ecg]
        store.execute(oxygen)
        store.execute(ecg)
    }

    // MARK: Private

    private func oxygen(_ readings: [(id: String, at: Date, fraction: Double)], error: String?) {
        if let error { log.error("blood oxygen query failed: \(error, privacy: .public)") }
        for reading in readings {
            post(
                HealthReadingForm(
                    id: reading.id, kind: "spo2", measuredAt: healthTimestamp(reading.at),
                    spo2: spo2Percent(reading.fraction)))
        }
    }

    private func electrocardiograms(_ found: [HKElectrocardiogram], error: String?) {
        if let error { log.error("ECG query failed: \(error, privacy: .public)") }
        for ecg in found { readTrace(of: ecg) }
    }

    /// Collects the voltages of one ECG, then posts it with its classification and heart rate.
    private func readTrace(of ecg: HKElectrocardiogram) {
        let id = ecg.uuid.uuidString
        let at = healthTimestamp(ecg.startDate)
        let classification = classificationName(ecg.classification)
        let heartRate = ecg.averageHeartRate.map {
            Int($0.doubleValue(for: HKUnit.count().unitDivided(by: .minute())).rounded())
        }
        let hz = ecg.samplingFrequency?.doubleValue(for: .hertz()) ?? 0
        // Only touched by the query's handler, which HealthKit calls one at a time
        let volts = OSAllocatedUnfairLock(initialState: [Double]())
        let query = HKElectrocardiogramQuery(ecg) { @Sendable [weak self] _, result in
            switch result {
            case .measurement(let measurement):
                if let volt = measurement.quantity(for: .appleWatchSimilarToLeadI) {
                    let value = volt.doubleValue(for: .volt())
                    volts.withLock { $0.append(value) }
                }
            case .done:
                let all = volts.withLock { $0 }
                Task { @MainActor in
                    let short = shortenTrace(volts: all, hz: hz)
                    self?.post(
                        HealthReadingForm(
                            id: id, kind: "ecg", measuredAt: at, ecgClassification: classification,
                            ecgHeartRate: heartRate, ecgTrace: short?.trace, ecgTraceHz: short?.hz))
                }
            case .error(let error):
                let reason = String(describing: error)
                Task { @MainActor in
                    self?.log.error(
                        "ECG \(id, privacy: .public) not read: \(reason, privacy: .public)")
                }
            @unknown default:
                break
            }
        }
        queries.append(query)
        store.execute(query)
    }

    private func post(_ form: HealthReadingForm) {
        let api = api
        let log = log
        Task {
            do {
                try await api.sendHealthReading(form)
                log.info("\(form.kind, privacy: .public) \(form.id, privacy: .public) sent")
            } catch {
                log.error(
                    "\(form.kind, privacy: .public) \(form.id, privacy: .public) not sent: \(String(describing: error), privacy: .public)"
                )
            }
        }
    }
}
