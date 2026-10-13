import { expect, test } from "vite-plus/test";
import { toE164 } from "./phone";

test("toE164 follows the five rules of auth-layer §7.1", () => {
  expect(toE164("0722 123-456")).toBe("+40722123456");
  expect(toE164("(0722).123.456")).toBe("+40722123456");
  expect(toE164("0040 700 000 001")).toBe("+40700000001");
  expect(toE164("700000001")).toBe("+40700000001");
  expect(toE164("+40 700 000 001")).toBe("+40700000001");
  expect(toE164("+1 650 555 0101")).toBe("+16505550101");
});
