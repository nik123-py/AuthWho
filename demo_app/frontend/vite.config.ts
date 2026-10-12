import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The demo backend runs on port 8100 (DEMO_BACKEND_URL overrides it, for example in the
// end-to-end tests). Proxying /api keeps its session cookie same-origin.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: env.DEMO_BACKEND_URL ?? "http://localhost:8100",
        changeOrigin: false,
      },
    },
  },
});
