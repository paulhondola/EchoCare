import { describe, expect, it } from "vitest";
import { sparkline } from "./sparkline";

const MIN = 60_000;

describe("sparkline", () => {
  it("draws the highest value at the top and the lowest at the bottom", () => {
    const path = sparkline(
      [
        { t: 0, v: 60 },
        { t: 5 * MIN, v: 80 },
      ],
      0,
      10 * MIN,
      100,
      20,
    );
    expect(path).toBe("M0.0 20.0L50.0 0.0");
  });

  it("breaks the line at a missing value and at a long silence", () => {
    const path = sparkline(
      [
        { t: 0, v: 70 },
        { t: 5 * MIN, v: null },
        { t: 10 * MIN, v: 70 },
        { t: 60 * MIN, v: 70 },
      ],
      0,
      60 * MIN,
      60,
      10,
    );
    expect(path.match(/M/g)).toHaveLength(3);
    expect(path).not.toContain("L");
  });

  it("is empty with nothing to draw", () => {
    expect(sparkline([{ t: 0, v: null }], 0, MIN, 10, 10)).toBe("");
    expect(sparkline([], 0, MIN, 10, 10)).toBe("");
  });
});
