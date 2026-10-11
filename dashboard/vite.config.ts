import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite-plus";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
  // type checking through tsgolint replaces tsc --noEmit (ADR-002)
  lint: { options: { typeAware: true, typeCheck: true } },
  // Markdown keeps the repository's compact tables; oxfmt would pad every column
  fmt: { ignorePatterns: ["*.md"] },
});
