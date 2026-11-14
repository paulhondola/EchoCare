import SwiftUI

/// „Help is coming” (design 2026-11-14, watch senior UI): shown after „Nu mă simt bine”, „Nu” or a
/// prompt's timeout. It says the team is being told, „Încercăm din nou…” when the phone hasn't
/// answered in 20 s, and ✓ only once the phone acks, which it does after FastAPI has recorded the
/// event (04 §3). The ✓ goes home after a minute; a tap goes home at any time. The times live here, not in
/// `Monitor.tick`, which stops while monitoring is paused.
struct HelpComingView: View {
    let alert: Alert
    let dismiss: () -> Void

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let phase = alert.phase(nowMs: Int64(context.date.timeIntervalSince1970 * 1_000))
            ScrollView {
                VStack(spacing: 8) {
                    if phase == .received {
                        Image(systemName: "checkmark")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 64, height: 64)
                            .background(Palette.yes, in: Circle())
                            .accessibilityHidden(true)
                        Text("help_received").font(.headline)
                        Text("help_answer_phone").font(.body)
                    } else {
                        ProgressView()
                            .controlSize(.large)
                            .padding(.vertical, 6)
                        Text("help_sending").font(.headline)
                        Text(phase == .retrying ? "help_retrying" : "help_keep_phone")
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                }
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
            }
            .contentShape(Rectangle())
            // Any phase: with no ack (phone off, no network) the senior must not be stuck here. The
            // event stays queued and is resent either way
            .onTapGesture { dismiss() }
        }
        .task(id: alert.receivedAtMs) {
            guard alert.receivedAtMs != nil else { return }
            try? await Task.sleep(for: .milliseconds(Timings.helpShownMs))
            if !Task.isCancelled { dismiss() }
        }
    }
}
