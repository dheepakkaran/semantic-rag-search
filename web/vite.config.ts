import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev requests to /api go to the Node service, so the browser only ever
    // talks to one origin and CORS never comes up during development.
    proxy: {
      "/api": { target: "http://localhost:3011", changeOrigin: true },
    },
  },
});
