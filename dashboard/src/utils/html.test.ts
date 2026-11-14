import { expect, test } from "vite-plus/test";
import { escapeHtml } from "./html";

// Leaflet's tooltips take HTML; a senior's name is typed by a medic (design 2026-11-14 §7)
test("a name cannot become markup", () => {
  expect(escapeHtml(`<img src=x onerror="alert('1')">&`)).toBe(
    "&lt;img src=x onerror=&quot;alert(&#39;1&#39;)&quot;&gt;&amp;",
  );
});

test("an ordinary name is unchanged", () => {
  expect(escapeHtml("Maria Popescu-Ionescu")).toBe("Maria Popescu-Ionescu");
});
