import { expect, test } from "vite-plus/test";
import type { IncidentCall, LiveCall } from "../services/api";
import { alarmWords, currentCode, highlight, liveCallDone } from "./live";

const AT = "2026-11-14T15:00:00Z";

function call(over: Partial<IncidentCall>): IncidentCall {
  return {
    id: "c1",
    trigger: "campaign",
    attempt: 1,
    state: "in_progress",
    started_at: AT,
    ended_at: null,
    final_severity: null,
    final_certainty: null,
    reason: null,
    summary: null,
    handover_answered: null,
    reports: [],
    turns: [],
    ...over,
  };
}

const report = (severity: string) => ({
  source: "rules",
  severity,
  certainty: null,
  reason: "",
  quote: null,
  at: AT,
});

test("alarm words come from the reason when no quote was stored", () => {
  expect(
    alarmWords({ source: "alarm_tier1", quote: null, reason: "A spus: «mă doare în piept»" }),
  ).toBe("mă doare în piept");
});

test("a stored quote wins over the reason", () => {
  expect(
    alarmWords({ source: "alarm_tier2", quote: "am căzut", reason: "A spus: «altceva»" }),
  ).toBe("am căzut");
});

test("an alarm with no words in its reason has none", () => {
  expect(
    alarmWords({ source: "alarm_tier1", quote: null, reason: "A cerut un operator (tasta 9)" }),
  ).toBeNull();
});

test("only alarm reports carry alarm words", () => {
  expect(alarmWords({ source: "rules", quote: "ceva", reason: "A spus: «ceva»" })).toBeNull();
});

test("highlight matches without case or diacritics and keeps the original text", () => {
  expect(highlight("Mă doare în piept tare", "ma doare in piept")).toEqual([
    "",
    "Mă doare în piept",
    " tare",
  ]);
});

test("highlight finds nothing when the words are absent", () => {
  expect(highlight("bine", "piept")).toBeNull();
});

test("the final severity is the code once known", () => {
  expect(currentCode(call({ final_severity: "red", reports: [report("green")] }), "green")).toBe(
    "red",
  );
});

test("during the call the newest report is the code", () => {
  expect(currentCode(call({ reports: [report("yellow"), report("red")] }), "green")).toBe("red");
});

test("before any report the code is the starting severity", () => {
  expect(currentCode(call({}), "yellow")).toBe("yellow");
});

test("a call is done once it leaves the live list", () => {
  const live = { id: "a" } as LiveCall;
  expect(liveCallDone("a", [live])).toBe(false);
  expect(liveCallDone("a", [])).toBe(true);
});
