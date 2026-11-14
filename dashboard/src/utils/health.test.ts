import { expect, test } from "vite-plus/test";
import { ecgLabel, tracePoints } from "./health";

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
