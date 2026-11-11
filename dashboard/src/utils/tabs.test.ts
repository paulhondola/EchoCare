import { expect, test } from "vite-plus/test";
import { nextTab } from "./tabs";

const KEYS = ["a", "b", "c"] as const;

test("nextTab wraps the arrows and jumps with Home and End", () => {
  expect(nextTab(KEYS, "c", "ArrowRight")).toBe("a");
  expect(nextTab(KEYS, "a", "ArrowLeft")).toBe("c");
  expect(nextTab(KEYS, "b", "Home")).toBe("a");
  expect(nextTab(KEYS, "b", "End")).toBe("c");
  expect(nextTab(KEYS, "b", "Enter")).toBeNull();
});
