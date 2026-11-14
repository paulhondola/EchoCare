import SwiftUI

/// The senior's watch home (UC-09, UC-10), ported from `SeniorHomeScreen.kt`: monitoring state and
/// pulse, start and stop (the phone's „Pornește monitorizarea” starts it too), and „Nu mă simt
/// bine”, which reaches FastAPI through the phone. Debug builds add the synthetic-anomaly buttons.
/// `EchoCareWatchApp` swaps in `AreYouOkView` while `Monitor.prompt` is set.
struct HomeView: View {
    let monitor: Monitor
    @State private var sending = false

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Text("app_name")
                    .font(.headline)
                if monitor.startFailed {
                    Line(text: "permission_needed")
                    Button("grant_permission") { Task { await monitor.start() } }
                }
                Text(monitor.running ? LocalizedStringKey("monitor_active") : "monitor_off")
                    .font(.body)
                    .multilineTextAlignment(.center)
                if monitor.running {
                    Text(verbatim: pulseLine)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if monitor.running {
                    Button("stop_monitoring") { monitor.stop() }
                } else {
                    Button("start_monitoring") { Task { await monitor.start() } }
                        .disabled(monitor.starting)
                }
                Button(sending ? LocalizedStringKey("call_me_sending") : "call_me") { callMe() }
                    .disabled(sending)
                #if DEBUG
                    Button("force_high_pulse") { monitor.forceAnomaly(type: "high_pulse_at_rest") }
                    Button("force_inactivity") { monitor.forceAnomaly(type: "inactivity") }
                    Button("force_fall") { monitor.forceAnomaly(type: "fall") }
                #endif
            }
        }
    }

    private var pulseLine: String {
        guard let bpm = monitor.lastHeartRate else {
            return String(localized: "heart_rate_waiting")
        }
        // %1$lld reads 64 bits; Swift's Int is 32 on arm64_32 watches
        return String(format: String(localized: "heart_rate"), Int64(bpm))
    }

    /// Queued at once, as on Wear OS; „Se trimite…” for a moment keeps a second tap from sending a
    /// second request.
    private func callMe() {
        guard !sending else { return }
        sending = true
        monitor.callMe()
        Task {
            try? await Task.sleep(for: .seconds(2))
            sending = false
        }
    }
}

private struct Line: View {
    let text: LocalizedStringKey

    var body: some View {
        Text(text)
            .font(.footnote)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
    }
}
