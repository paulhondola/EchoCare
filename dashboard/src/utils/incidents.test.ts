import { expect, test } from "vite-plus/test";
import type { Incident } from "../services/api";
import { columns, fold, initials, matchesIncident, shortId, since } from "./incidents";

const NOW = Date.parse("2026-10-14T12:00:00Z");
const ago = (min: number) => new Date(NOW - min * 60_000).toISOString();

function incident(over: Partial<Incident>): Incident {
  return {
    id: "3f37c1bb-b293-47a1-8264-ca270d2a9c7b",
    senior_full_name: "Maria Ionescu",
    senior_form_of_address: "doamna Maria",
    status: "open",
    reason: "Puls ridicat în repaus",
    opened_at: ago(5),
    taken_by_name: null,
    taken_at: null,
    handover_answered: false,
    ...over,
  };
}

test("shortId keeps the first block of the uuid", () => {
  expect(shortId("3f37c1bb-b293-47a1-8264-ca270d2a9c7b")).toBe("3f37c1bb");
});

test("since counts minutes, then hours, then shows the date", () => {
  expect(since(ago(0.5), NOW)).toBe("acum câteva secunde");
  expect(since(ago(4), NOW)).toBe("acum 4 min");
  expect(since(ago(125), NOW)).toBe("acum 2 h 5 min");
  expect(since(ago(60 * 30), NOW)).not.toMatch(/^acum/);
  // a clock a little ahead of the server's never shows a negative time
  expect(since(ago(-1), NOW)).toBe("acum câteva secunde");
});

test("initials takes the first two words", () => {
  expect(initials("Elena Vasilescu")).toBe("EV");
  expect(initials("ana maria popescu")).toBe("AM");
  expect(initials(null)).toBe("");
});

test("the filter ignores case and diacritics", () => {
  expect(fold("Cod Roșu ȘI Țară")).toBe("cod rosu si tara");
  const i = incident({ taken_by_name: "Ion Popescu" });
  expect(matchesIncident(i, "")).toBe(true);
  expect(matchesIncident(i, "IONESCU")).toBe(true);
  expect(matchesIncident(i, "repaus")).toBe(true);
  expect(matchesIncident(i, "popescu")).toBe(true);
  expect(matchesIncident(i, "3f37")).toBe(true);
  expect(matchesIncident(i, "Gheorghe")).toBe(false);
});

test("columns put the longest wait first and the latest resolved first", () => {
  const list = [
    incident({ id: "a", opened_at: ago(2) }),
    incident({ id: "b", opened_at: ago(9) }),
    incident({ id: "c", status: "in_progress", opened_at: ago(30), taken_at: ago(3) }),
    incident({ id: "d", status: "in_progress", opened_at: ago(20), taken_at: ago(10) }),
    incident({ id: "e", status: "resolved", opened_at: ago(90), taken_at: ago(80) }),
    incident({ id: "f", status: "resolved", opened_at: ago(60), taken_at: ago(40) }),
  ];
  const c = columns(list);
  expect(c.open.map((i) => i.id)).toEqual(["b", "a"]);
  expect(c.in_progress.map((i) => i.id)).toEqual(["d", "c"]);
  expect(c.resolved.map((i) => i.id)).toEqual(["f", "e"]);
});
