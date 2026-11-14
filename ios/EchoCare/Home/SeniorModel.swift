import Foundation
import Observation

/// What „Pornește monitorizarea” shows.
enum Monitoring: Equatable {
    case idle, starting, started, failed
}

/// The banner after what the phone last heard from the watch. An event or check-in within two
/// check-in intervals means the watch is monitoring, however it was started (the phone or the
/// watch's own button); `.started` with nothing heard for two intervals since the last message or
/// the start, or with the watch app gone, goes back to idle, so the button invites a new start.
/// A start in flight is left alone.
func monitoringAfter(
    _ state: Monitoring, seen: WatchSeen, startedAt: Date?, now: Date, interval: TimeInterval
) -> Monitoring {
    if state == .starting { return state }
    if seen.appInstalled == false { return state == .started ? .idle : state }
    let window = 2 * interval
    if let heard = seen.lastHeard, now.timeIntervalSince(heard) <= window { return .started }
    guard state == .started else { return state }
    if let freshest = [seen.lastHeard, startedAt].compactMap({ $0 }).max(),
        now.timeIntervalSince(freshest) <= window
    {
        return .started
    }
    return .idle
}

/// The senior's own home: GET /seniors/{id} for the one senior their grant names (seniors §3.3),
/// ported from android/app/.../home/SeniorViewModel.kt, its own-home half. The senior's page is
/// also the home of the iPhone app that relays the watch (G5), so it holds „Pornește monitorizarea”.
@Observable @MainActor
final class SeniorModel {
    private(set) var page: Load<SeniorPage> = .loading

    /// A weather warning is in force (Q5).
    private(set) var warning = false

    /// The call the card answers; nil when none is due or on production (design §6.2).
    private(set) var mock: MockCall?

    /// The short call history (UC-12); nil until read.
    private(set) var calls: [CallRow]?

    /// What „Sunați-mă” shows (UC-10).
    private(set) var callMe: CallMe = .idle

    /// What „Pornește monitorizarea” shows.
    private(set) var monitoring: Monitoring = .idle

    private let api: ApiClient
    private let location: LocationHelper
    private let startWatch: @MainActor () async throws -> Void
    private let startHealth: @MainActor () -> Void
    private let restartHealth: @MainActor () -> Void
    private let watchSeen: @MainActor () -> WatchSeen
    private let now: @MainActor () -> Date
    private let checkInInterval: TimeInterval
    private var startedAt: Date?
    private var reading: Task<Void, Never>?
    private var answering = false

    init(
        api: ApiClient = ApiClient(tokens: FirebaseTokenSource()),
        location: LocationHelper = LocationHelper(),
        startWatch: @escaping @MainActor () async throws -> Void = {
            try await WatchLink.shared.startMonitoring()
        },
        startHealth: @escaping @MainActor () -> Void = { HealthSync.shared.start() },
        restartHealth: @escaping @MainActor () -> Void = { HealthSync.shared.restart() },
        watchSeen: @escaping @MainActor () -> WatchSeen = { WatchLink.shared.seen },
        now: @escaping @MainActor () -> Date = { Date() },
        checkInInterval: TimeInterval = WatchLink.checkInInterval
    ) {
        self.api = api
        self.location = location
        self.startWatch = startWatch
        self.startHealth = startHealth
        self.restartHealth = restartHealth
        self.watchSeen = watchSeen
        self.now = now
        self.checkInInterval = checkInInterval
    }

    /// „Sunați-mă”. No retry: a failed tap shows `.notSent` and the senior taps again, with a new
    /// id. A signed-out session ends on the next reread. The fix rides along when there is one;
    /// the request never waits for it (UC-09 §5).
    func requestCall() {
        guard callMe != .sending else { return }
        callMe = .sending
        var form = manualRequest()
        if let fix = location.lastKnown(), fix.horizontalAccuracy >= 0 {
            form.latitude = fix.coordinate.latitude
            form.longitude = fix.coordinate.longitude
            form.locationAccuracyM = fix.horizontalAccuracy
        }
        let api = api
        let request = form
        Task { callMe = callMeAfter(await answer { try await api.sendEvent(request) }) }
    }

    /// Reads the page, the calls, the warning and the card. A read still under way is out of date;
    /// left running, it could land after this one.
    func load() async {
        location.prepare()
        startHealth()
        refreshMonitoring()
        reading?.cancel()
        let read = Task { await readAll() }
        reading = read
        await withTaskCancellationHandler {
            await read.value
        } onCancel: {
            read.cancel()
        }
    }

    private func readAll() async {
        let api = api
        let read = await answer { try await Self.readSenior(api) }
        // A cancelled read says nothing about the connection
        guard !Task.isCancelled else { return }
        page = page.after(read)
        guard case .ok(let senior) = read else { return }
        // A failed read keeps the last list, as the page keeps its last answer
        if case .ok(let rows) = await answer({ try await api.calls(id: senior.id) }),
            !Task.isCancelled
        {
            calls = rows
        }
        if case .ok(let me) = await answer({ try await api.me() }), !Task.isCancelled {
            warning = me.warningActive
        }
        // Only a definite answer changes the card (design §6.2)
        let card = await readMock { try await api.mockCall() }
        guard !Task.isCancelled else { return }
        mock = cardAfterRead(status: card.status, body: card.body, previous: mock)
    }

    /// Posts the card's answer. Once the server answered, even with a 409, the card goes and the
    /// page rereads; a lost connection or a 5xx keeps the card to press again (design §6.2).
    func answerMock(_ body: MockAnswer) async {
        guard let call = mock, !answering else { return }
        answering = true
        defer { answering = false }
        let api = api
        let status = await postStatus { try await api.mockAnswer(id: call.callId, body: body) }
        if answerSettled(status: status) {
            mock = nil
            await load()
        }
    }

    /// „Pornește monitorizarea”: asks the watch to start (design, Monitoring runs inside an
    /// HKWorkoutSession). `.started` only once `startWatchApp` succeeded. Tappable again once
    /// started or failed.
    func startMonitoring() async {
        guard monitoring != .starting else { return }
        monitoring = .starting
        do {
            try await startWatch()
            startedAt = now()
            monitoring = .started
            // The first start of a fresh install ran before the grant and read nothing
            restartHealth()
        } catch {
            monitoring = .failed
            // The grant happens before startWatchApp, which can still throw
            restartHealth()
        }
    }

    /// The banner after what the phone heard from the watch; run on each reread of the home.
    func refreshMonitoring() {
        monitoring = monitoringAfter(
            monitoring, seen: watchSeen(), startedAt: startedAt, now: now(),
            interval: checkInInterval)
    }

    /// The one senior the grant names: the first of the senior's own list (04 §1).
    private static func readSenior(_ api: ApiClient) async throws -> SeniorPage {
        let rows = try await api.seniors(role: "senior")
        guard let id = rows.first?.id else { throw ApiError.http(status: 404, body: "") }
        return try await api.senior(id: id)
    }
}
