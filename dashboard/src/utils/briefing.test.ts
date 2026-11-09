import { describe, expect, it } from "vitest";
import { citedOn, DIRECTION } from "./briefing";
import { time } from "./labels";

describe("DIRECTION", () => {
  it("labels each trend direction in Romanian", () => {
    expect(DIRECTION).toEqual({
      worse: "În înrăutățire",
      better: "În îmbunătățire",
      steady: "Stabil",
    });
  });
});

describe("citedOn", () => {
  const calls = [
    { id: "a", started_at: "2026-11-01T09:30:00Z" },
    { id: "b", started_at: null },
  ];
  it("formats the date of a known call", () => {
    expect(citedOn("a", calls)).toBe(time.format(Date.parse("2026-11-01T09:30:00Z")));
  });
  it("falls back for an unknown call or an unstarted one", () => {
    expect(citedOn("zzz", calls)).toBe("apel anterior");
    expect(citedOn("b", calls)).toBe("apel anterior");
  });
});
