import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // macOS may resolve Vite's default `localhost` binding to IPv6 only. Pin
    // the dev server to IPv4 so http://127.0.0.1:5173 works consistently.
    host: "127.0.0.1",
    // API and media both live on the backend in dev; proxy so the frontend never
    // needs to know a second origin (and CORS stays a non-issue).
    proxy: {
      "/api": "http://localhost:8000",
      "/media": "http://localhost:8000",
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
