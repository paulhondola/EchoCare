import { time } from "./labels";

// Trend direction as text only: no red, yellow or green (design §5 C)
export const DIRECTION: Record<"worse" | "better" | "steady", string> = {
  worse: "În înrăutățire",
  better: "În îmbunătățire",
  steady: "Stabil",
};

/** The cited call's date, or "apel anterior" when it is not in the list */
export function citedOn(
  callId: string,
  calls: { id: string; started_at: string | null }[],
): string {
  const at = calls.find((c) => c.id === callId)?.started_at;
  return at ? time.format(Date.parse(at)) : "apel anterior";
}
