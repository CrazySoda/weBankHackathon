import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api -> the FastAPI backend so the client can use a
// single relative prefix in both dev and the nginx container.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      watch: {
        usePolling: env.VITE_USE_POLLING === "true",
        interval: 300,
      },
      proxy: {
        "/api": {
          target: env.VITE_API_TARGET || "http://localhost:8000",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
