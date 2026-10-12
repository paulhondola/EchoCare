import type { IncidentOutcome, SeniorAddress } from "./api";

export const time = new Intl.DateTimeFormat("ro-RO", { dateStyle: "short", timeStyle: "short" });

// The five outcomes of 04 §2, in the order a dispatcher thinks of them
export const OUTCOMES: { value: IncidentOutcome; label: string }[] = [
  { value: "senior_ok", label: "Seniorul este bine" },
  { value: "team_sent", label: "Echipă trimisă" },
  { value: "called_112", label: "Apel la 112" },
  { value: "not_reached", label: "Nu a putut fi contactat" },
  { value: "false_alarm", label: "Alarmă falsă" },
];

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
