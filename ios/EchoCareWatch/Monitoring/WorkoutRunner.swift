import CoreMotion
import Foundation
import HealthKit
import os

enum WorkoutError: Error {
    case healthUnavailable
    case notAuthorized
}

/// The real `SensorSource` (design "Watch app"): an `HKWorkoutSession` (`.other`, indoor) keeps the
/// app running with the wrist down and its live builder delivers heart rate every ~5 s;
/// `CMMotionManager` reads the accelerometer at 50 Hz, in g; `CMPedometer` counts the day's steps.
/// Spike results: all three keep arriving with the wrist down. On stop the workout is discarded, so
/// nothing lands in Health.
///
/// Main-actor isolated. HealthKit and CoreMotion call back on their own queues: the delegate
/// methods are `nonisolated`, pull the plain values out, and hop to the main actor.
@MainActor
final class WorkoutRunner: NSObject, SensorSource {
    /// Set by `handle(_ workoutConfiguration:)` when the phone ran `startWatchApp(with:)`; the next
    /// start uses it.
    var configuration: HKWorkoutConfiguration?

    private let store = HKHealthStore()
    private let motion = CMMotionManager()
    private let pedometer = CMPedometer()
    private let log = Logger(subsystem: "ro.echocare.watch", category: "workout")

    private var session: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?
    private var onHeartRate: ((Int64, Int) -> Void)?
    private var onAcceleration: ((Int64, Float) -> Void)?
    private var onSteps: ((Int64, Int) -> Void)?
    private var onEnded: (() -> Void)?

    func start(
        onHeartRate: @escaping (Int64, Int) -> Void,
        onAcceleration: @escaping (Int64, Float) -> Void,
        onSteps: @escaping (Int64, Int) -> Void,
        onEnded: @escaping () -> Void
    ) async throws {
        guard session == nil else { return }
        guard HKHealthStore.isHealthDataAvailable() else { throw WorkoutError.healthUnavailable }
        try await store.requestAuthorization(
            toShare: [HKObjectType.workoutType()], read: [HKQuantityType(.heartRate)])
        // Reading access is never revealed; sharing workouts is what the session needs
        guard store.authorizationStatus(for: HKObjectType.workoutType()) == .sharingAuthorized
        else {
            throw WorkoutError.notAuthorized
        }
        guard session == nil else { return }

        let config = configuration ?? Self.defaultConfiguration()
        configuration = nil
        let session = try HKWorkoutSession(healthStore: store, configuration: config)
        let builder = session.associatedWorkoutBuilder()
        builder.dataSource = HKLiveWorkoutDataSource(
            healthStore: store, workoutConfiguration: config)
        session.delegate = self
        builder.delegate = self
        self.session = session
        self.builder = builder
        self.onHeartRate = onHeartRate
        self.onAcceleration = onAcceleration
        self.onSteps = onSteps
        self.onEnded = onEnded

        let now = Date()
        session.startActivity(with: now)
        do {
            try await builder.beginCollection(at: now)
        } catch {
            log.error("beginCollection failed: \(error.localizedDescription, privacy: .public)")
            stop()
            throw error
        }
        startMotion()
        startPedometer()
        log.info("workout started")
    }

    func stop() {
        // Callbacks go first: nothing reaches the monitor after a stop
        onHeartRate = nil
        onAcceleration = nil
        onSteps = nil
        onEnded = nil
        motion.stopAccelerometerUpdates()
        pedometer.stopUpdates()
        guard let session else { return }
        let builder = self.builder
        self.session = nil
        self.builder = nil
        session.end()
        Task {
            do {
                try await builder?.endCollection(at: Date())
            } catch {
                self.log.error(
                    "endCollection failed: \(error.localizedDescription, privacy: .public)")
            }
            // Monitoring isn't exercise: nothing is saved to Health
            builder?.discardWorkout()
            self.log.info("workout stopped")
        }
    }

    /// The same configuration the phone's `startWatchApp(with:)` sends (Task 1).
    static func defaultConfiguration() -> HKWorkoutConfiguration {
        let config = HKWorkoutConfiguration()
        config.activityType = .other
        config.locationType = .indoor
        return config
    }

    // MARK: Sensors

    private func startMotion() {
        guard motion.isAccelerometerAvailable else {
            log.error("no accelerometer")
            return
        }
        motion.accelerometerUpdateInterval = 1 / Timings.accelerometerHz
        // CMLogItem timestamps count from boot; this turns them into wall-clock time
        let bootMs = (Date().timeIntervalSince1970 - ProcessInfo.processInfo.systemUptime) * 1_000
        // Delivered on the main queue, so already on the main actor
        motion.startAccelerometerUpdates(to: .main) { @Sendable [weak self] data, _ in
            guard let data else { return }
            let a = data.acceleration
            let g = Float((a.x * a.x + a.y * a.y + a.z * a.z).squareRoot())
            let atMs = Int64(bootMs + data.timestamp * 1_000)
            MainActor.assumeIsolated { self?.onAcceleration?(atMs, g) }
        }
    }

    private func startPedometer() {
        guard CMPedometer.isStepCountingAvailable() else {
            log.error("no step counting")
            return
        }
        // shortcut: counts from the day the session started; a session across midnight keeps
        // counting yesterday's steps (the demo runs minutes)
        let midnight = Calendar.current.startOfDay(for: Date())
        pedometer.startUpdates(from: midnight) { @Sendable [weak self] data, error in
            guard let data, error == nil else { return }
            let steps = data.numberOfSteps.intValue
            let atMs = Int64(data.endDate.timeIntervalSince1970 * 1_000)
            Task { @MainActor in self?.onSteps?(atMs, steps) }
        }
    }

    private func heartRate(_ bpm: Int, atMs: Int64) {
        onHeartRate?(atMs, bpm)
    }

    private func sessionEnded() {
        guard session != nil else { return }
        let ended = onEnded
        stop()
        ended?()
    }
}

extension WorkoutRunner: HKWorkoutSessionDelegate {
    nonisolated func workoutSession(
        _ workoutSession: HKWorkoutSession, didChangeTo toState: HKWorkoutSessionState,
        from fromState: HKWorkoutSessionState, date: Date
    ) {
        let ended = toState == .ended || toState == .stopped
        let raw = toState.rawValue
        Task { @MainActor in
            self.log.info("session state \(raw)")
            if ended { self.sessionEnded() }
        }
    }

    nonisolated func workoutSession(
        _ workoutSession: HKWorkoutSession, didFailWithError error: any Error
    ) {
        let reason = error.localizedDescription
        Task { @MainActor in
            self.log.error("session failed: \(reason, privacy: .public)")
            self.sessionEnded()
        }
    }
}

extension WorkoutRunner: HKLiveWorkoutBuilderDelegate {
    nonisolated func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {}

    nonisolated func workoutBuilder(
        _ workoutBuilder: HKLiveWorkoutBuilder, didCollectDataOf collectedTypes: Set<HKSampleType>
    ) {
        let type = HKQuantityType(.heartRate)
        guard collectedTypes.contains(type),
            let quantity = workoutBuilder.statistics(for: type)?.mostRecentQuantity()
        else { return }
        let bpm = Int(quantity.doubleValue(for: .count().unitDivided(by: .minute())).rounded())
        let atMs = Int64(Date().timeIntervalSince1970 * 1_000)
        Task { @MainActor in self.heartRate(bpm, atMs: atMs) }
    }
}
