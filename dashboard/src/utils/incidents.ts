import type { Incident, IncidentStatus } from "../services/api";
import { time } from "./labels";

/** The four tabs of the incident dossier */
export type DossierTab = "access" | "transcript" | "event" | "resolve";

/** The first block of a uuid, for a card's corner: "#3f37c1bb" */
export function shortId(id: string): string {
  return id.split("-")[0];
}

/** "acum 4 min", "acum 2 h 5 min"; a day or more shows the date */
export function since(iso: string, now: number): string {
  const ms = now - Date.parse(iso);
  const m = Math.max(0, Math.floor(ms / 60_000));
  if (m < 1) return "acum câteva secunde";
  if (m < 60) return `acum ${m} min`;
  if (m < 24 * 60) return `acum ${Math.floor(m / 60)} h ${m % 60} min`;
  return time.format(Date.parse(iso));
}

/** "Elena Vasilescu" → "EV" */
export function initials(name: string | null | undefined): string {
  return (name ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

/** Lower case without diacritics, so "rosu" finds "Roșu" */
export function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

/** Whether an incident matches the board's filter text; "#3f37c1bb" finds the id as cards show it */
export function matchesIncident(i: Incident, query: string): boolean {
  const q = fold(query.trim().replace(/^#/, ""));
  if (!q) return true;
  return fold(
    [i.id, i.senior_full_name, i.senior_form_of_address, i.reason, i.taken_by_name ?? ""].join(" "),
  ).includes(q);
}

const at = (iso: string | null) => (iso ? Date.parse(iso) : 0);

/**
 * The board's three columns. Open and in progress put the longest wait first; resolved
 * puts the latest first. The API sends no resolve time, so the take time stands in.
 */
export function columns(list: Incident[]): Record<IncidentStatus, Incident[]> {
  const of = (s: IncidentStatus) => list.filter((i) => i.status === s);
  return {
    open: of("open").sort((a, b) => at(a.opened_at) - at(b.opened_at)),
    in_progress: of("in_progress").sort(
      (a, b) => at(a.taken_at ?? a.opened_at) - at(b.taken_at ?? b.opened_at),
    ),
    resolved: of("resolved").sort(
      (a, b) => at(b.taken_at ?? b.opened_at) - at(a.taken_at ?? a.opened_at),
    ),
  };
}

/** The call that decided an incident: its red call, else the newest (design 2026-11-14 §5) */
export function decidingCall<
  T extends { final_severity: string | null; started_at: string | null },
>(calls: T[]): T | null {
  const red = calls.find((c) => c.final_severity === "red");
  if (red) return red;
  const started = (c: T) => (c.started_at ? Date.parse(c.started_at) : 0);
  return calls.reduce<T | null>((a, c) => (a === null || started(c) > started(a) ? c : a), null);
}
