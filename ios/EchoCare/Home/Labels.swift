// The words and colours of the server's states, codes and triggers, ported from
// android/app/.../home/Routes.kt. Each value is a `Localizable.xcstrings` key. A value this build
// does not know has none: the server may add one later (ADR-001 §2.3).

/// The label of each enrollment state (05 §1).
let STATE_LABELS = [
    "draft": "state_draft", "submitted": "state_submitted", "accepted": "state_accepted",
    "active": "state_active", "refused": "state_refused", "wrong_number": "state_wrong_number",
    "unreachable": "state_unreachable", "withdrawn": "state_withdrawn",
]

/// The colour of each state's chip, the same as on the dashboard (dashboard/src/utils/labels.ts).
let STATE_TONES: [String: Tone] = [
    "draft": .muted, "submitted": .link, "accepted": .link, "active": .verde, "refused": .galben,
    "wrong_number": .galben, "unreachable": .galben, "withdrawn": .muted,
]

/// The label of each code (03 §8).
let CODE_LABELS = ["green": "code_green", "yellow": "code_yellow", "red": "code_red"]

/// The colour of each code's chip and of a card's bar.
let CODE_TONES: [String: Tone] = ["green": .verde, "yellow": .galben, "red": .rosu]

/// What started each call (05 §1), as the dashboard names it. Unknown: shown as it is.
let TRIGGER_LABELS = [
    "campaign": "trigger_campaign", "watch": "trigger_watch", "manual": "trigger_manual",
    "welcome": "trigger_welcome",
]

/// A call's state (05 §1), for a call with no final code yet. Unknown: shown as it is.
let CALL_STATE_LABELS = [
    "queued": "call_queued", "ringing": "call_ringing", "in_progress": "call_in_progress",
    "unanswered": "call_unanswered", "failed": "call_failed", "completed": "call_completed",
    "handed_over": "call_handed_over", "dropped": "call_dropped", "canceled": "call_canceled",
]

/// A transcript answer's question (05 §2) under the medic's transcript. Unknown: shown raw.
let ANSWER_FIELDS = [
    "feeling": "answer_feeling", "orientation": "answer_orientation", "shelter": "answer_shelter",
    "identity": "answer_identity", "consent": "consent_label",
]

/// A transcript answer's value (03 §3): the codes in Romanian. The days are Romanian already; a
/// value this build does not know shows raw.
let ANSWER_VALUES = [
    "ok": "answer_ok", "unwell": "answer_unwell", "yes": "answer_yes", "no": "answer_no",
    "unknown": "answer_unknown",
]

/// The event behind an incident (05 §1), as the dashboard names it. Unknown: shown as it is.
let EVENT_LABELS = [
    "sos_button": "event_sos_button", "fall": "event_fall",
    "high_pulse_at_rest": "event_high_pulse_at_rest",
    "inactivity": "event_inactivity", "manual_request": "event_manual_request",
]
