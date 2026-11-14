import { expect, test } from "vite-plus/test";
import type { SeniorView } from "../services/api";
import { deviceWarnings, showsWatch } from "./equipment";

const base = {
  equipment: ["smartphone", "watch"],
  watch_state: null,
  app_signed_in: false,
  enrollment_state: "active",
};

test("the watch hides only when the equipment says there is none", () => {
  expect(showsWatch({ equipment: null })).toBe(true);
  expect(showsWatch({ equipment: undefined })).toBe(true);
  expect(showsWatch({ equipment: ["smartphone", "watch"] })).toBe(true);
  expect(showsWatch({ equipment: [] })).toBe(false);
  expect(showsWatch({ equipment: ["smartphone"] })).toBe(false);
});

test("a declared watch with no data and an unopened app both warn", () => {
  expect(deviceWarnings(base)).toEqual([
    "Ceas înregistrat, nu a trimis date",
    "Pacientul nu a deschis aplicația",
  ]);
});

test("the warnings stop once the watch reports and the app is opened", () => {
  expect(deviceWarnings({ ...base, watch_state: "ok", app_signed_in: true })).toEqual([]);
});

test("a declared home node warns until its first room reading", () => {
  const node = { ...base, equipment: ["smartphone", "home_node"], app_signed_in: true };
  expect(deviceWarnings(node)).toEqual(["Senzor din casă înregistrat, nu a trimis date"]);
  expect(deviceWarnings({ ...node, room: null })).toHaveLength(1);
  const reading = { state: "ok", room_state: "ok" } as unknown as SeniorView["room"];
  expect(deviceWarnings({ ...node, room: reading })).toEqual([]);
});

test("no warnings when not stated, before acceptance, or from an older API", () => {
  expect(deviceWarnings({ ...base, equipment: null })).toEqual([]);
  expect(deviceWarnings({ ...base, enrollment_state: "submitted" })).toEqual([]);
  expect(deviceWarnings({ ...base, enrollment_state: "accepted" })).toHaveLength(2);
  expect(deviceWarnings({ ...base, watch_state: "ok", app_signed_in: null })).toEqual([]);
});
