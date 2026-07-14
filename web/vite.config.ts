import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // API and media both live on the backend in dev; proxy so the frontend never
    // needs to know a second origin (and CORS stays a non-issue).
    proxy: {
      "/api": "http://localhost:8000",
      "/media": "http://localhost:8000",
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
