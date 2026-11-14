import { describe, expect, it } from "vitest";
import { progressParts } from "./campaigns";

describe("progressParts", () => {
  it("lists the non-zero counts in order", () => {
    expect(
      progressParts({ total: 5, waiting: 2, green: 1, yellow: 0, red: 1, canceled: 1 }).map((p) => [
        p.label,
        p.n,
      ]),
    ).toEqual([
      ["în așteptare", 2],
      ["verde", 1],
      ["roșu", 1],
      ["anulate", 1],
    ]);
  });
  it("is empty for a campaign that queued nobody", () => {
    expect(
      progressParts({ total: 0, waiting: 0, green: 0, yellow: 0, red: 0, canceled: 0 }),
    ).toEqual([]);
  });
});
