import { expect, test } from "vite-plus/test";
import { dots, ecgLabel, tracePoints } from "./health";

test("every verdict has its Romanian label", () => {
  expect(ecgLabel("sinus_rhythm")).toBe("Ritm sinusal");
  expect(ecgLabel("atrial_fibrillation")).toBe("Fibrilație atrială");
  expect(ecgLabel("inconclusive_low_heart_rate")).toBe("Neconcludent: puls scăzut");
  expect(ecgLabel("inconclusive_high_heart_rate")).toBe("Neconcludent: puls ridicat");
  expect(ecgLabel("inconclusive_poor_reading")).toBe("Neconcludent: citire slabă");
  expect(ecgLabel("inconclusive_other")).toBe("Neconcludent");
  expect(ecgLabel("unrecognized")).toBe("Neclasificat");
});
test("an unknown verdict shows as it is", () => expect(ecgLabel("new_thing")).toBe("new_thing"));
test("trace points are spaced by the rate", () =>
  expect(tracePoints([5, 6, 7], 128)).toEqual([
    { t: 0, v: 5 },
    { t: 7.8125, v: 6 },
    { t: 15.625, v: 7 },
  ]));
test("dots span the box, the highest value on top", () =>
  expect(
    dots(
      [
        { t: 0, v: 90 },
        { t: 1000, v: 100 },
      ],
      0,
      1000,
      300,
      48,
    ),
  ).toEqual([
    { x: 0, y: 48 },
    { x: 300, y: 0 },
  ]));
test("a dot outside the window is dropped", () =>
  expect(dots([{ t: 2000, v: 95 }], 0, 1000, 300, 48)).toEqual([]));
test("a single reading is one dot, mid-height", () =>
  expect(dots([{ t: 500, v: 97 }], 0, 1000, 300, 48)).toEqual([{ x: 150, y: 24 }]));
