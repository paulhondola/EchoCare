import adapter from "@sveltejs/adapter-static";
import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite-plus";

export default defineConfig({
  plugins: [
    tailwindcss(),
    // Single-page mode (ADR-003): dist/index.html serves every route, and the Caddyfile falls back to it.
    // index.html is safe as the fallback because nothing is prerendered.
    sveltekit({ adapter: adapter({ pages: "dist", assets: "dist", fallback: "index.html" }) }),
  ],
  server: { port: 5173 },
  // type checking through tsgolint replaces tsc --noEmit (ADR-002); svelte-check covers .svelte files
  lint: {
    ignorePatterns: [".svelte-kit/**", "dist/**"],
    options: { typeAware: true, typeCheck: true },
  },
  // Markdown keeps the repository's compact tables; .svelte goes through oxfmt's bundled Svelte printer
  fmt: { ignorePatterns: ["*.md", ".svelte-kit/**", "dist/**"], svelte: true },
});
