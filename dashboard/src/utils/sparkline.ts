/** One reading on the line: when (ms) and its value, null when the watch sent none */
export type Point = { t: number; v: number | null };

// A hole longer than two missed 15-minute check-ins (06 §3) breaks the line, so a watch left
// off shows as a gap while one check-in per bucket still draws
const GAP_MS = 35 * 60_000;

/**
 * An SVG path for `points` across [from, to] in a w × h box, the highest value at the top.
 * A missing value or a long silence starts a new segment. "" when nothing is drawable.
 */
export function sparkline(points: Point[], from: number, to: number, w: number, h: number): string {
  const values = points.flatMap((p) => (p.v === null ? [] : [p.v]));
  if (!values.length || to <= from) return "";
  const lo = Math.min(...values);
  const span = Math.max(...values) - lo || 1;
  const x = (t: number) => (((t - from) / (to - from)) * w).toFixed(1);
  const y = (v: number) => (h - ((v - lo) / span) * h).toFixed(1);
  let path = "";
  let last: number | null = null;
  for (const p of points) {
    if (p.v === null) {
      last = null;
      continue;
    }
    const joined = last !== null && p.t - last <= GAP_MS;
    path += `${joined ? "L" : "M"}${x(p.t)} ${y(p.v)}`;
    last = p.t;
  }
  return path;
}
