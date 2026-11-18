import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Flask dev server; the Vite proxy keeps requests same-origin so the backend's
// cross-origin write guard still applies unchanged.
const backend = process.env.GMC_BACKEND ?? "http://127.0.0.1:5001";

export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "../app/spa_dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: backend } },
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // CSS is stubbed in tests, except the token file that tokens.test.ts reads as text.
    css: { include: [/index\.css/] },
    restoreMocks: true,
  },
});
