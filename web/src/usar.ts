import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useCarregar<T>(url: string | null) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const recarregar = useCallback(async () => {
    if (!url) return;
    setCarregando(true);
    try { setDados(await api.get<T>(url)); setErro(""); }
    catch (e) { setErro((e as Error).message); }
    finally { setCarregando(false); }
  }, [url]);
  useEffect(() => { recarregar(); }, [recarregar]);
  return { dados, erro, carregando, recarregar, setDados };
}
