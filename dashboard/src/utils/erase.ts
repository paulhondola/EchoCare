/** Why an erasure was refused, in Romanian (04 §2, design 2026-11-14). */
export function eraseRefusalText(reason: string | undefined): string {
  switch (reason) {
    case "call_live":
      return "Un apel este în desfășurare. Încercați după ce se încheie.";
    case "incident_open":
      return "Seniorul are un incident nerezolvat. Rezolvați-l mai întâi.";
    default:
      return "Ștergerea a eșuat. Încercați din nou.";
  }
}
