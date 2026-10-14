/**
 * Rows as CSV (RFC 4180): quoted only when a cell needs it, CRLF between rows. A cell that
 * starts like a formula gets a leading ' so Excel shows it as text (OWASP CSV injection):
 * a name typed as "=HYPERLINK(…)" or a number like "+16505550101".
 */
export function toCsv(rows: string[][]): string {
  const cell = (raw: string) => {
    const v = /^[=+@\t\r-]/.test(raw) ? `'${raw}` : raw;
    return /[",\r\n]/.test(v) ? `"${v.replaceAll('"', '""')}"` : v;
  };
  return rows.map((r) => r.map(cell).join(",")).join("\r\n");
}

/** Hands the text to the browser as a file; the byte-order mark keeps Excel reading UTF-8 */
export function download(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  // Firefox and Safari read the URL after click() returns: revoking at once can cancel the file
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
