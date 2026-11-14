import type { Point } from "./sparkline";

// Apple's ECG verdicts (04 §1, ADR-008); an unknown one shows as it is
const ECG_LABELS: Record<string, string> = {
  sinus_rhythm: "Ritm sinusal",
  atrial_fibrillation: "Fibrilație atrială",
  inconclusive_low_heart_rate: "Neconcludent: puls scăzut",
  inconclusive_high_heart_rate: "Neconcludent: puls ridicat",
  inconclusive_poor_reading: "Neconcludent: citire slabă",
  inconclusive_other: "Neconcludent",
  unrecognized: "Neclasificat",
};

export const ecgLabel = (classification: string): string =>
  ECG_LABELS[classification] ?? classification;

/** The trace as points `1000 / hz` ms apart, from 0 */
export const tracePoints = (trace: number[], hz: number): Point[] =>
  trace.map((v, i) => ({ t: (i * 1000) / hz, v }));

/**
 * Where each point sits in a w × h box across [from, to], the highest value at the top, as
 * `sparkline` scales it. Spot readings are too far apart to join, so they are drawn as dots.
 * A flat series sits mid-height; points outside the window are dropped.
 */
export function dots(
  points: Point[],
  from: number,
  to: number,
  w: number,
  h: number,
): { x: number; y: number }[] {
  const inside = points.flatMap((p) =>
    p.v !== null && p.t >= from && p.t <= to ? [{ t: p.t, v: p.v }] : [],
  );
  if (!inside.length || to <= from) return [];
  const lo = Math.min(...inside.map((p) => p.v));
  const span = Math.max(...inside.map((p) => p.v)) - lo;
  return inside.map((p) => ({
    x: ((p.t - from) / (to - from)) * w,
    y: span ? h - ((p.v - lo) / span) * h : h / 2,
  }));
}
