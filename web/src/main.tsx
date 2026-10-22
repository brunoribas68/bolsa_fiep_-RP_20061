import { CssBaseline, ThemeProvider, useMediaQuery } from "@mui/material";
import React, { useMemo } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { AvisosProvider } from "./componentes/avisos";
import { criarTema } from "./tema";

function Raiz() {
  const escuro = useMediaQuery("(prefers-color-scheme: dark)");
  const tema = useMemo(() => criarTema(escuro ? "dark" : "light"), [escuro]);
  return (
    <ThemeProvider theme={tema}>
      <CssBaseline enableColorScheme />
      <BrowserRouter>
        <AuthProvider>
          <AvisosProvider>
            <App />
          </AvisosProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}

ReactDOM.createRoot(document.getElementById("raiz")!).render(<React.StrictMode><Raiz /></React.StrictMode>);
