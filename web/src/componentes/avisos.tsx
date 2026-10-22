import { Alert, Snackbar } from "@mui/material";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Tipo = "success" | "error" | "info" | "warning";
const Ctx = createContext<(msg: string, tipo?: Tipo) => void>(() => undefined);

export function AvisosProvider({ children }: { children: ReactNode }) {
  const [aviso, setAviso] = useState<{ msg: string; tipo: Tipo; chave: number } | null>(null);
  const avisar = useCallback((msg: string, tipo: Tipo = "success") => setAviso({ msg, tipo, chave: Date.now() }), []);
  return (
    <Ctx.Provider value={avisar}>
      {children}
      <Snackbar key={aviso?.chave} open={!!aviso} autoHideDuration={aviso?.tipo === "error" ? 8000 : 3500}
                onClose={() => setAviso(null)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        {aviso ? <Alert severity={aviso.tipo} variant="filled" onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Ctx.Provider>
  );
}

export const useAvisos = () => useContext(Ctx);
