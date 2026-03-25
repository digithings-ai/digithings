import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  // Dev: serve at root so /src/main.tsx resolves correctly
  // Build: relative paths so assets work on any host path (GitHub Pages, etc.)
  base: command === "build" ? "./" : "/",
  build: {
    outDir: ".",
    emptyOutDir: false,
    assetsDir: "assets",
  },
}));
