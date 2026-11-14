import type { IncidentCall, LiveCall } from "../services/api";

type Level = "green" | "yellow" | "red";

const ALARMS = new Set(["alarm_tier1", "alarm_tier2"]);

/**
 * The senior's words behind an alarm report (design 2026-11-14 §4). A live call stores no
 * `quote`; the hand-over writes them into the reason as „A spus: «…»”.
 */
export function alarmWords(r: { source: string; quote: string | null; reason: string }) {
  if (!ALARMS.has(r.source)) return null;
  if (r.quote) return r.quote;
  return /«([^»]+)»/.exec(r.reason)?.[1] ?? null;
}

// Lowercase without diacritics, one character per character, so indexes map back
function fold(s: string): string {
  return Array.from(s, (c) => c.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase()).join("");
}

/** The turn split around `words`, ignoring case and diacritics; null when absent */
export function highlight(turn: string, words: string): [string, string, string] | null {
  const at = fold(turn).indexOf(fold(words));
  if (at < 0) return null;
  const end = at + Array.from(words).length;
  const chars = Array.from(turn);
  return [chars.slice(0, at).join(""), chars.slice(at, end).join(""), chars.slice(end).join("")];
}

/** The code to show for a call: final once known, else the newest report, else the start */
export function currentCode(call: IncidentCall, starting: Level): Level {
  return (call.final_severity ?? call.reports.at(-1)?.severity ?? starting) as Level;
}

/** True once the call has left GET /calls/live */
export function liveCallDone(id: string, live: LiveCall[]): boolean {
  return !live.some((c) => c.id === id);
}
