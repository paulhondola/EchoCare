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
