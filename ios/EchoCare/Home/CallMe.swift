import SwiftUI

// „Sunați-mă” on the senior's home (UC-10): asks FastAPI for a wellbeing call. The server queues it
// and the dialer rings the phone on its next tick; a tap while one is queued joins that call (04 §3).
// Ported from android/app/.../home/CallMe.kt.

/// What the button shows.
enum CallMe: Equatable {
    case idle, sending, coming, notSent
}

/// A fresh id per tap, so only a resend of this very tap is a duplicate (04 §3).
func manualRequest(id: String = UUID().uuidString, now: Date = .now) -> EventForm {
    EventForm(id: id, type: "manual_request", measuredAt: now.formatted(.iso8601), source: "phone")
}

/// The state once the post answered. A 200 without a call means the server kept the event and
/// queued none, so nothing is coming; that, a refusal and a lost connection all invite another tap.
func callMeAfter(_ answer: Answer<EventResult>) -> CallMe {
    if case .ok(let result) = answer, result.callId != nil { return .coming }
    return .notSent
}

struct CallMeButton: View {
    let state: CallMe
    let action: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            switch state {
            case .coming: Banner("call_me_sent", tone: .verde)
            case .notSent: Banner("call_me_failed", tone: .rosu)
            default: EmptyView()
            }
            SnButton("call_me", kind: .success, fullWidth: true, minHeight: 56, action: action)
                .disabled(state == .sending)
        }
        .padding(.bottom, 16)
    }
}
