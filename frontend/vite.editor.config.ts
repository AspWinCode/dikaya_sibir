import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Production build for the App Builder (served from the site root)
export default defineConfig({
  base: "/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "@editor": resolve(__dirname, "src/editor"),
      "@shared": resolve(__dirname, "src/shared"),
    },
  },
  build: {
    outDir: "dist/editor",
    rollupOptions: {
      input: resolve(__dirname, "src/editor/index.html"),
    },
    chunkSizeWarningLimit: 1000,
  },
});
