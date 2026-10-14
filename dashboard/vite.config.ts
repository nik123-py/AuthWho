import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The AuthWho API runs on port 8000 (AUTHWHO_API_URL overrides it). Proxying /v1, including the
// live WebSocket, keeps the dashboard same-origin, so the admin API needs no CORS.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      "/v1": {
        target: env.AUTHWHO_API_URL ?? "http://localhost:8000",
        changeOrigin: false,
        ws: true,
      },
    },
  },
});
