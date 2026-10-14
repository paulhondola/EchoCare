/** What the person types, turned into E.164 before sending (auth-layer §7.1). The server normalizes again. */
export function toE164(typed: string): string {
  const n = typed.replace(/[\s\-.()]/g, "");
  if (n.startsWith("00")) return `+${n.slice(2)}`;
  if (n.startsWith("0")) return `+40${n.slice(1)}`;
  if (n.startsWith("7")) return `+40${n}`;
  return n; // a leading + stays as it is; anything else Firebase refuses as invalid
}

/** A Romanian E.164 number as people read it: "0722 111 222", "021 456 7788". Others stay as they are. */
export function formatPhone(e164: string): string {
  const m = /^\+40(\d{9})$/.exec(e164);
  if (!m) return e164;
  const n = `0${m[1]}`;
  // Bucharest landlines have a three-digit prefix (021, 031); the rest four (0722, 0264)
  if (/^0[23]1/.test(n)) return `${n.slice(0, 3)} ${n.slice(3, 6)} ${n.slice(6)}`;
  return `${n.slice(0, 4)} ${n.slice(4, 7)} ${n.slice(7)}`;
}
