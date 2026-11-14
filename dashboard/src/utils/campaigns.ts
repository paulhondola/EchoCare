import type { Campaign, CampaignKind, WarningLevel } from "../services/api";
import type { Tone } from "./labels";

export const KIND_LABELS: Record<CampaignKind, string> = { heat: "Caniculă", cold: "Ger" };
export const LEVEL_LABELS: Record<WarningLevel, string> = {
  yellow: "Cod galben",
  red: "Cod roșu",
};

/** The non-zero progress counts, in the order a dispatcher reads them (04 §1) */
export function progressParts(
  p: Campaign["progress"],
): { key: string; label: string; n: number; tone: Tone }[] {
  const parts: { key: string; label: string; n: number; tone: Tone }[] = [
    { key: "waiting", label: "în așteptare", n: p.waiting, tone: "muted" },
    { key: "green", label: "verde", n: p.green, tone: "verde" },
    { key: "yellow", label: "galben", n: p.yellow, tone: "galben" },
    { key: "red", label: "roșu", n: p.red, tone: "rosu" },
    { key: "canceled", label: "anulate", n: p.canceled, tone: "muted" },
  ];
  return parts.filter((part) => part.n > 0);
}
