import { expect, test, vi } from "vite-plus/test";
import { downloadJson, eraseRefusalText } from "./erase";

test("explains each erase refusal (04 §2)", () => {
  expect(eraseRefusalText("call_live")).toBe(
    "Un apel este în desfășurare. Încercați după ce se încheie.",
  );
  expect(eraseRefusalText("incident_open")).toBe(
    "Seniorul are un incident nerezolvat. Rezolvați-l mai întâi.",
  );
});

test("falls back for anything else", () => {
  expect(eraseRefusalText(undefined)).toBe("Ștergerea a eșuat. Încercați din nou.");
  expect(eraseRefusalText("not_allowed")).toBe("Ștergerea a eșuat. Încercați din nou.");
});

test("downloadJson revokes the blob URL after click returns, not synchronously", () => {
  vi.useFakeTimers();
  const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  const clicked: { href: string; download: string }[] = [];
  vi.stubGlobal("document", {
    createElement: () => ({
      href: "",
      download: "",
      click() {
        clicked.push({ href: this.href, download: this.download });
      },
    }),
  });

  try {
    downloadJson("echocare-senior-1.json", { ok: true });
    expect(clicked).toEqual([{ href: "blob:test", download: "echocare-senior-1.json" }]);
    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(10_000);
    expect(revoke).toHaveBeenCalledWith("blob:test");
  } finally {
    create.mockRestore();
    revoke.mockRestore();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  }
});
