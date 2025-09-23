import { defineConfig } from "vite";

// vite.config.ts
export default {
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
};
);
