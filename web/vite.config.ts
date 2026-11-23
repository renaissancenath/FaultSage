import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Build output is served by both the local daemon and FaultSage Cloud.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/faultsage/static/app",
    emptyOutDir: true,
    sourcemap: false,
    assetsInlineLimit: 0,
  },
  server: {
    fs: { allow: [".."] },
    proxy: { "/api": "http://127.0.0.1:8000", "/auth": "http://127.0.0.1:8765", "/healthz": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom", globals: false, include: ["src/**/*.test.tsx", "src/**/*.test.ts"] },
});
