import { ApiError } from "../../services/api";

/** What a refused Preiau or Rezolvă tells the dispatcher (04 §0, §2) */
export function refusalMessage(e: unknown, action: "take" | "resolve"): string {
  if (!(e instanceof ApiError)) return "Nu am putut trimite. Încercați din nou.";
  switch (e.reason) {
    case "already_done":
      return action === "take"
        ? `Incidentul a fost preluat deja de ${e.takenByName ?? "un alt dispecer"}.`
        : "Incidentul a fost deja rezolvat.";
    case "wrong_state":
      return "Incidentul s-a schimbat între timp.";
    case "not_allowed":
      return "Nu aveți dreptul să faceți asta.";
    case "not_found":
      return "Incidentul nu mai există.";
    default:
      return `Nu am putut trimite (${e.message}).`;
  }
}
