import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    port: 3002,
    allowedHosts: true,
    proxy: {
      "/api": "http://localhost:9999",
      "/media": "http://localhost:9999",
    },
  },
});
