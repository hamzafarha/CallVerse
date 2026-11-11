/**
 * Vite configuration of the back office: the React plugin, the dev server port (5174) and the proxy to the
 * FastAPI backend (the same as the front office, on another port).
 */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies the API so the browser talks to one origin.
const api = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  // Where the app lives on the server: "/" in development; "/back-office/" online, where one address serves
  // both apps (BACK_OFFICE_BASE is set by the Hugging Face Space build, deploy/huggingface/Dockerfile).
  base: process.env.BACK_OFFICE_BASE ?? "/",
  // Allow bigger JavaScript files before warning (the chart and animation libraries are large).
  build: { chunkSizeWarningLimit: 1200 },
  server: {
    port: 5174,
    // strictPort: stop with an error instead of moving to another port, because the backend only accepts
    // these exact origins (cors_origins in configs/app.yaml).
    strictPort: true,
    // Forward /api, /ws (WebSocket), /docs and /openapi.json to the backend.
    proxy: {
      "/api": { target: api, changeOrigin: true },
      "/ws": { target: api.replace("http", "ws"), ws: true },
      "/docs": { target: api, changeOrigin: true },
      "/openapi.json": { target: api, changeOrigin: true },
    },
  },
  // `npm run preview` (serves the built app) uses the same port.
  preview: { port: 5174 },
});
