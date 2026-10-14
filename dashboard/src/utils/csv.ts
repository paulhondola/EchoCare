/** Rows as CSV (RFC 4180): quoted only when a cell needs it, CRLF between rows */
export function toCsv(rows: string[][]): string {
  const cell = (v: string) => (/[",\r\n]/.test(v) ? `"${v.replaceAll('"', '""')}"` : v);
  return rows.map((r) => r.map(cell).join(",")).join("\r\n");
}

/** Hands the text to the browser as a file; the byte-order mark keeps Excel reading UTF-8 */
export function download(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
