import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000" },
  },
  build: {
    target: "es2022",
    // MapLibre is ~1 MB on its own; it is split out and loaded with the map.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("maplibre-gl")) return "maplibre";
        },
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
