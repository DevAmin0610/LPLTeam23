import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // The workshop serves the dev server through CloudFront.
    allowedHosts: [".cloudfront.net"],
    // Send /api calls to the backend on this machine, so the browser only
    // needs to reach the frontend (no CORS or second public URL needed).
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    clearMocks: true,
    restoreMocks: true,
    css: false,
  },
});