import { expect, test } from "vite-plus/test";
import { toCsv } from "./csv";

test("toCsv quotes only the cells that need it", () => {
  expect(
    toCsv([
      ["Nume", "Telefon"],
      ["Maria Ionescu", "0722 111 222"],
      ['Ion "Nea" Pop', "a,b"],
      ["Rând\nnou", ""],
    ]),
  ).toBe('Nume,Telefon\r\nMaria Ionescu,0722 111 222\r\n"Ion ""Nea"" Pop","a,b"\r\n"Rând\nnou",');
});
