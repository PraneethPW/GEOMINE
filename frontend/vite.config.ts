import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    manifest: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (/\/(react|react-dom|scheduler)\//.test(id)) return "react";
          if (id.includes("/react-router/")) return "router";
          if (id.includes("/three/") || id.includes("/@react-three/")) return "three";
          if (id.includes("/maplibre-gl/")) return "map";
          if (/\/(framer-motion|motion-dom|motion-utils)\//.test(id)) return "motion";
        },
      },
    },
  },
});
