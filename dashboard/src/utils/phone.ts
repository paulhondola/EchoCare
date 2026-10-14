/** What the person types, turned into E.164 before sending (auth-layer §7.1). The server normalizes again. */
export function toE164(typed: string): string {
  const n = typed.replace(/[\s\-.()]/g, "");
  if (n.startsWith("00")) return `+${n.slice(2)}`;
  if (n.startsWith("0")) return `+40${n.slice(1)}`;
  if (n.startsWith("7")) return `+40${n}`;
  return n; // a leading + stays as it is; anything else Firebase refuses as invalid
}
