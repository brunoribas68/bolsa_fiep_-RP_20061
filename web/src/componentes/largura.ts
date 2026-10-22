import { useEffect, useRef, useState } from "react";

/** Largura do contêiner: o gráfico desenha nessa largura (em vez de encolher), e o texto fica legível no celular. */
export function useLargura<T extends HTMLElement>(padrao = 640, min = 300, max = 760) {
  const ref = useRef<T>(null);
  const [w, setW] = useState(padrao);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(Math.max(min, Math.min(max, e.contentRect.width)))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [min, max]);
  return [ref, w] as const;
}
