import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const here = import.meta.dirname;

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  define: {
    "process.env.NODE_ENV": JSON.stringify(command === "build" ? "production" : "development"),
  },
  build: {
    outDir: resolve(here, "../src/framelab/_static"),
    emptyOutDir: true,
    target: "es2022",
    sourcemap: false,
    lib: {
      entry: resolve(here, "src/index.tsx"),
      formats: ["es"],
      fileName: () => "framelab.js",
      cssFileName: "framelab",
    },
    // Library mode keeps ES output unminified; the whole bundle travels in every
    // notebook widget's comm_open, so minify it at the Rolldown level.
    rolldownOptions: { output: { codeSplitting: false, minify: true } },
  },
  server: {
    port: 5173,
    proxy: { "/ws": { target: "ws://127.0.0.1:8765", ws: true } },
  },
}));
