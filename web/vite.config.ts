import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento (npm run dev) as chamadas /api vão para a API em http://127.0.0.1:8000.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {   // bibliotecas em arquivos separados: o navegador guarda em cache entre versões do app
        manualChunks: { react: ["react", "react-dom", "react-router-dom"], mui: ["@mui/material", "@emotion/react", "@emotion/styled"] },
      },
    },
  },
});
