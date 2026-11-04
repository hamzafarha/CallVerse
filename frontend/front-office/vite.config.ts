/**
 * Vite configuration of the front office: the React plugin, the dev server port (5173) and the proxy to the
 * FastAPI backend.
 *
 * Two ways to start it:
 * - `npm run dev:front`: http://localhost:5173, only on this PC (normal development);
 * - `npm run dev:phone`: https on every network address of the PC, so a phone on the same Wi-Fi can open
 *   https://<PC address>:5173/phone and use its microphone (phones require https for it). The certificate
 *   comes from `callverse phone-cert` (frontend/certs/, ignored by git).
 */
import react from "@vitejs/plugin-react";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// The dev server proxies the API so the browser talks to one origin.
const api = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";
const certs = fileURLToPath(new URL("../certs/", import.meta.url));

/** The local HTTPS certificate for the phone demo (made by `callverse phone-cert`). */
function phoneHttps() {
  const cert = `${certs}callverse-dev.crt`;
  const key = `${certs}callverse-dev.key`;
  if (!existsSync(cert) || !existsSync(key)) {
    throw new Error("No HTTPS certificate for the phone demo: run `callverse phone-cert` in the project folder first.");
  }
  return { cert: readFileSync(cert), key: readFileSync(key) };
}

export default defineConfig(({ mode }) => {
  const phone = mode === "phone"; // npm run dev:phone
  return {
    plugins: [react()],
    // Allow bigger JavaScript files before warning (the chart and animation libraries are large).
    build: { chunkSizeWarningLimit: 1200 },
    server: {
      port: 5173,
      // strictPort: stop with an error instead of moving to another port, because the backend only accepts
      // these exact origins (cors_origins in configs/app.yaml).
      strictPort: true,
      // Phone mode: listen on the Wi-Fi too (host: true) and serve https.
      host: phone ? true : undefined,
      https: phone ? phoneHttps() : undefined,
      // Forward /api, /ws (WebSocket), /docs and /openapi.json to the backend.
      proxy: {
        "/api": { target: api, changeOrigin: true },
        "/ws": { target: api.replace("http", "ws"), ws: true },
        "/docs": { target: api, changeOrigin: true },
        "/openapi.json": { target: api, changeOrigin: true },
      },
    },
    // `npm run preview` (serves the built app) uses the same port.
    preview: { port: 5173 },
  };
});
