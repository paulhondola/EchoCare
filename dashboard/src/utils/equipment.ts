// Which device panels and warnings a senior's page shows, from the equipment the medic
// declared at registration (UC-01, UC-13, design 2026-11-14). DAS is never the senior,
// so every warning that applies is shown.

type Declared = { equipment?: string[] | null };
type Devices = Declared & {
  watch_state?: string | null;
  app_signed_in?: boolean | null;
  // The home node's latest reading; null until its first one (P20)
  room?: unknown;
  enrollment_state: string;
};

// Not stated (registered before the declaration existed) shows the watch as before
export const showsWatch = (s: Declared): boolean =>
  s.equipment == null || s.equipment.includes("watch");

export const WATCH_WARNING = "Ceas înregistrat, nu a trimis date";

// Before DAS accepts there is nothing to set up yet
const WARNED_STATES = new Set(["accepted", "active"]);

export function deviceWarnings(s: Devices): string[] {
  const kit = s.equipment;
  if (kit == null || !WARNED_STATES.has(s.enrollment_state)) return [];
  const warnings: string[] = [];
  if (kit.includes("watch") && s.watch_state == null) warnings.push(WATCH_WARNING);
  if (kit.includes("home_node") && s.room == null)
    warnings.push("Senzor din casă înregistrat, nu a trimis date");
  // `null` is an older API that does not say: no warning
  if (kit.includes("smartphone") && s.app_signed_in === false)
    warnings.push("Pacientul nu a deschis aplicația");
  return warnings;
}
