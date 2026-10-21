import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, quandoSessaoExpirar } from "./api";
import type { Usuario } from "./tipos";

interface Ctx {
  usuario: Usuario | null; carregando: boolean;
  entrar: (email: string, senha: string) => Promise<void>; sair: () => Promise<void>;
  pode: (acao: "editar" | "admin") => boolean;
}
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    api.get<Usuario>("/api/auth/eu").then(setUsuario).catch(() => setUsuario(null)).finally(() => setCarregando(false));
    quandoSessaoExpirar(() => setUsuario(null));
  }, []);

  const entrar = useCallback(async (email: string, senha: string) => {
    setUsuario(await api.post<Usuario>("/api/auth/login", { email, senha }));
  }, []);
  const sair = useCallback(async () => {
    await api.post("/api/auth/sair").catch(() => undefined);
    setUsuario(null);
  }, []);
  const pode = useCallback((acao: "editar" | "admin") =>
    !!usuario && (usuario.papel === "admin" || (acao === "editar" && usuario.papel === "colaborador")), [usuario]);

  return <AuthCtx.Provider value={{ usuario, carregando, entrar, sair, pode }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
