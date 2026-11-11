import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Dev server — editor at "/", runtime at "/app/", one dev server
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
      "@editor": resolve(__dirname, "src/editor"),
      "@runtime": resolve(__dirname, "src/runtime"),
      "@shared": resolve(__dirname, "src/shared"),
    },
  },
  server: {
    port: process.env.PORT ? parseInt(process.env.PORT) : 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["src/test-setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      exclude: ["src/api/generated/**", "**/*.d.ts"],
    },
  },
});
