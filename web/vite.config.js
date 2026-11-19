import { defineConfig } from "vite";
import solid from "vite-plugin-solid";

const device = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [solid()],
  server: {
    port: 5173,
    proxy: {
      "/api": device,
      "/stream.mjpg": device,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
