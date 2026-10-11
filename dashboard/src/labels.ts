import type { IncidentOutcome } from "./api";

export const time = new Intl.DateTimeFormat("ro-RO", { dateStyle: "short", timeStyle: "short" });

// The five outcomes of 04 §2, in the order a dispatcher thinks of them
export const OUTCOMES: { value: IncidentOutcome; label: string }[] = [
  { value: "senior_ok", label: "Seniorul este bine" },
  { value: "team_sent", label: "Echipă trimisă" },
  { value: "called_112", label: "Apel la 112" },
  { value: "not_reached", label: "Nu a putut fi contactat" },
  { value: "false_alarm", label: "Alarmă falsă" },
];
