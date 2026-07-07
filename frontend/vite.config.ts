import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev: Vite serves the SPA on its own port and proxies API calls to the
// FastAPI backend (ageo / ageo-demo, port 8000). Production: `npm run
// build` emits into src/ageo/interface/web/dist, which app.py serves
// directly - no dev server involved at runtime.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/tasks": "http://127.0.0.1:8000",
      "/catalog": "http://127.0.0.1:8000",
      "/settings": "http://127.0.0.1:8000",
      "/uploads": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "../src/ageo/interface/web/dist",
    emptyOutDir: true,
  },
});
