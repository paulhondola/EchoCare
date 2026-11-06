import type { IncidentOutcome, SeniorAddress } from "../services/api";

export const time = new Intl.DateTimeFormat("ro-RO", { dateStyle: "short", timeStyle: "short" });

/** "14:32:15", for transcript lines */
export const clock = new Intl.DateTimeFormat("ro-RO", { timeStyle: "medium" });

// Why a call rang and where it got to, as stored (05 §1); an unknown value shows as it is
export const TRIGGERS: Record<string, string> = {
  campaign: "Campanie",
  watch: "Ceas",
  manual: "Cerere „Sunați-mă”",
  welcome: "Apel de bun venit",
};

export const CALL_STATES: Record<string, string> = {
  queued: "în așteptare",
  ringing: "sună",
  in_progress: "în curs",
  unanswered: "nepreluat",
  failed: "eșuat",
  completed: "încheiat",
  handed_over: "transferat la DAS",
  dropped: "întrerupt",
  canceled: "anulat",
};

/** "2m 5s" between pick-up and end; null until both are known */
export function callLength(start: string | null, end: string | null): string | null {
  if (!start || !end) return null;
  const s = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 1000));
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

// The five outcomes of 04 §2, in the order a dispatcher thinks of them
export const OUTCOMES: { value: IncidentOutcome; label: string }[] = [
  { value: "senior_ok", label: "Senior OK" },
  { value: "team_sent", label: "Echipaj trimis" },
  { value: "called_112", label: "Apelat 112" },
  { value: "not_reached", label: "Nu a răspuns" },
  { value: "false_alarm", label: "Alarmă falsă" },
];

export type Tone = "verde" | "galben" | "rosu" | "link" | "muted";

// Enrollment states of 03 §1 as DAS sees them; an unknown state shows as it is
export const ENROLLMENT: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Ciornă", tone: "muted" },
  submitted: { label: "Cerere trimisă", tone: "link" },
  accepted: { label: "Acceptat", tone: "link" },
  active: { label: "Activ", tone: "verde" },
  refused: { label: "Consimțământ refuzat", tone: "galben" },
  wrong_number: { label: "Număr greșit", tone: "galben" },
  unreachable: { label: "Nu răspunde", tone: "galben" },
};

export function enrollment(state: string): { label: string; tone: Tone } {
  return ENROLLMENT[state] ?? { label: state, tone: "muted" };
}

// The codes of 03 §8 as the dashboard shows them
export const CODES: Record<string, { label: string; tone: Tone }> = {
  green: { label: "Cod verde", tone: "verde" },
  yellow: { label: "Cod galben", tone: "galben" },
  red: { label: "Cod roșu", tone: "rosu" },
};

export function code(c: string | null | undefined): { label: string; tone: Tone } | null {
  return c ? (CODES[c] ?? { label: c, tone: "muted" }) : null;
}

/** Chip colours per tone; full class names so Tailwind finds them */
export const TONE_CHIP: Record<Tone, string> = {
  verde: "bg-verde/15 text-verde-fg",
  galben: "bg-galben/15 text-galben-fg",
  rosu: "bg-rosu/15 text-rosu-fg",
  link: "bg-link/15 text-link",
  muted: "bg-line text-fg-soft",
};

export const TONE_DOT: Record<Tone, string> = {
  verde: "bg-verde",
  galben: "bg-galben",
  rosu: "bg-rosu",
  link: "bg-link",
  muted: "bg-fg-muted",
};

/** "Str. Florilor nr. 3, bl. A2, sc. B, et. 4, ap. 17", from what was filled in */
export function address(s: SeniorAddress): string {
  const parts = [
    [s.street, s.street_number && `nr. ${s.street_number}`].filter(Boolean).join(" "),
    s.block && `bl. ${s.block}`,
    s.staircase && `sc. ${s.staircase}`,
    s.floor && `et. ${s.floor}`,
    s.apartment && `ap. ${s.apartment}`,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "Adresă necompletată";
}
