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

/** Hands a JSON value to the browser as a downloaded file (04 §1, design 2026-11-14). */
export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  // Firefox and Safari read the URL after click() returns: revoking at once can cancel the file
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
