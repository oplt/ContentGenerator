import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("recharts") || id.includes("d3-")) {
            return "charts";
          }
          if (id.includes("@tanstack/react-query")) {
            return "query";
          }
          if (id.includes("react-router")) {
            return "router";
          }
          if (id.includes("react-dom") || id.includes("/react/")) {
            return "react";
          }
          if (id.includes("lucide-react")) {
            return "icons";
          }
          if (id.includes("@radix-ui")) {
            return "radix";
          }
          if (id.includes("zod") || id.includes("@hookform")) {
            return "forms";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
    allowedHosts: [
      "localhost",
      ".ngrok-free.app",
      "669a-2a02-a03f-8621-7401-76da-e73e-bf8f-dc50.ngrok-free.app",
    ],
  },
});
