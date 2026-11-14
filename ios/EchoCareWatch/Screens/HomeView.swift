import SwiftUI

/// The senior's watch home (UC-09, UC-10), after `SeniorHomeScreen.kt` and redesigned for seniors
/// (design 2026-11-14, watch senior UI): a calm status at a glance, the pulse, and one big
/// „Nu mă simt bine”, which reaches FastAPI through the phone and works whether monitoring runs or
/// not. The small pause button is the team's toggle; the phone's „Pornește monitorizarea” starts it
/// too. Debug builds add the synthetic-anomaly buttons below the fold. `EchoCareWatchApp` swaps in
/// `AreYouOkView` and `HelpComingView`.
struct HomeView: View {
    let monitor: Monitor

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 6) {
                    if monitor.startFailed {
                        Line(text: "permission_needed")
                        Button("grant_permission") { Task { await monitor.start() } }
                    }
                    Image(systemName: "heart.fill")
                        .font(.system(size: 44))
                        .foregroundStyle(monitor.running ? Palette.calm : .gray)
                        .accessibilityHidden(true)
                    Text(monitor.running ? LocalizedStringKey("all_good") : "monitor_off")
                        .font(.title3.bold())
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                    if monitor.running {
                        Text(verbatim: pulseLine)
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                    Button {
                        monitor.callMe()
                    } label: {
                        Text("call_me")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Palette.help)
                    .padding(.top, 4)
                    #if DEBUG
                        Button("force_high_pulse") {
                            monitor.forceAnomaly(type: "high_pulse_at_rest")
                        }
                        .padding(.top, 24)
                        Button("force_inactivity") { monitor.forceAnomaly(type: "inactivity") }
                        Button("force_fall") { monitor.forceAnomaly(type: "fall") }
                    #endif
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        if monitor.running {
                            monitor.stop()
                        } else {
                            Task { await monitor.start() }
                        }
                    } label: {
                        Image(systemName: monitor.running ? "pause.fill" : "play.fill")
                            .foregroundStyle(.gray)
                    }
                    .disabled(monitor.starting)
                    .accessibilityLabel(
                        monitor.running ? LocalizedStringKey("stop_monitoring") : "start_monitoring"
                    )
                }
            }
        }
    }

    private var pulseLine: String {
        guard let bpm = monitor.lastHeartRate else {
            return String(localized: "heart_rate_waiting")
        }
        // %1$lld reads 64 bits; Swift's Int is 32 on arm64_32 watches
        return String(format: String(localized: "heart_rate_plain"), Int64(bpm))
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
