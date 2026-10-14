import { expect, test } from "vite-plus/test";
import { formatPhone, toE164 } from "./phone";

test("toE164 follows the five rules of auth-layer §7.1", () => {
  expect(toE164("0722 123-456")).toBe("+40722123456");
  expect(toE164("(0722).123.456")).toBe("+40722123456");
  expect(toE164("0040 700 000 001")).toBe("+40700000001");
  expect(toE164("700000001")).toBe("+40700000001");
  expect(toE164("+40 700 000 001")).toBe("+40700000001");
  expect(toE164("+1 650 555 0101")).toBe("+16505550101");
});

test("formatPhone groups Romanian numbers and leaves others alone", () => {
  expect(formatPhone("+40722111222")).toBe("0722 111 222");
  expect(formatPhone("+40214567788")).toBe("021 456 7788");
  expect(formatPhone("+40264123456")).toBe("0264 123 456");
  expect(formatPhone("+16505550101")).toBe("+16505550101");
});
