import { expect, test } from "vite-plus/test";
import { eraseRefusalText } from "./erase";

test("explains each erase refusal (04 §2)", () => {
  expect(eraseRefusalText("call_live")).toBe(
    "Un apel este în desfășurare. Încercați după ce se încheie.",
  );
  expect(eraseRefusalText("incident_open")).toBe(
    "Seniorul are un incident nerezolvat. Rezolvați-l mai întâi.",
  );
  expect(eraseRefusalText("not_found")).toBe("Seniorul nu mai există.");
});

test("falls back for anything else", () => {
  expect(eraseRefusalText(undefined)).toBe("Ștergerea a eșuat. Încercați din nou.");
  expect(eraseRefusalText("not_allowed")).toBe("Ștergerea a eșuat. Încercați din nou.");
});
