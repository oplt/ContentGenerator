import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          router: ["react-router-dom"],
          query: ["@tanstack/react-query"],
          charts: ["recharts"],
        },
      },
    },
  },
    server: {
        host: true,  // Listen on all local addresses
        allowedHosts: [
            'localhost',
            '.ngrok-free.app',  // Allow all ngrok subdomains
            '669a-2a02-a03f-8621-7401-76da-e73e-bf8f-dc50.ngrok-free.app'  // Your specific URL
        ]
    },
});
