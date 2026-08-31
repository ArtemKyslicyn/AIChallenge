import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Local dev without Docker: the browser talks to :5173 only, so no CORS.
    // Behind nginx the same relative /api path is proxied to the api service.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
