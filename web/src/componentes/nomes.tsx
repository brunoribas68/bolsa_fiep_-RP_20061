import InfoOutlined from "@mui/icons-material/InfoOutlined";
import { Box, Chip, Stack, Tooltip, Typography } from "@mui/material";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import type { Catalogo, InfoAlgoritmo, InfoVariante } from "../tipos";
import { mono } from "./comum";

// O catálogo (nomes legíveis e explicações) muda só com uma versão nova do sistema: carrega uma vez.
let cache: Promise<Catalogo> | null = null;
export function useCatalogo() {
  const [cat, setCat] = useState<Catalogo | null>(null);
  useEffect(() => {
    cache ||= api.get<Catalogo>("/api/catalogo").catch(e => { cache = null; throw e; });
    let vivo = true;
    cache.then(c => vivo && setCat(c)).catch(() => {});
    return () => { vivo = false; };
  }, []);
  return cat;
}

/** "log_reg_l1 [dif_curva]" -> { alg: "log_reg_l1", variante: "dif_curva" } */
export function separarModelo(s: string | null | undefined) {
  const m = /^(.*?)\s*\[(.+)\]\s*$/.exec(s || "");
  return m ? { alg: m[1], variante: m[2] } : { alg: s || "", variante: null as string | null };
}

function Explicacao({ titulo, sub, familia, linhas, codigo }: {
  titulo: string; sub?: string; familia?: string; linhas: [string, string | undefined][]; codigo: string;
}) {
  return (
    <Box sx={{ p: .5, maxWidth: 360 }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="subtitle2">{titulo}</Typography>
        {familia && <Chip size="small" label={familia} sx={{ height: 20, fontSize: 11 }} />}
      </Stack>
      {sub && <Typography variant="body2" sx={{ opacity: .85 }}>{sub}</Typography>}
      {linhas.filter(([, t]) => t).map(([r, t]) => (
        <Typography key={r} variant="body2" sx={{ mt: .75 }}><b>{r}:</b> {t}</Typography>))}
      <Typography variant="caption" sx={{ display: "block", mt: .75, opacity: .7 }}>
        código: <Box component="span" sx={mono}>{codigo}</Box></Typography>
    </Box>
  );
}

export function ComDica({ dica, children }: { dica: ReactNode; children: ReactNode }) {
  return (
    <Tooltip title={dica} placement="bottom-start" describeChild enterDelay={250} enterTouchDelay={0} leaveTouchDelay={5000}
             slotProps={{ tooltip: { sx: { maxWidth: 380, bgcolor: "background.paper", color: "text.primary", boxShadow: 6,
                                           border: 1, borderColor: "divider" } } }}>
      <Box component="span" tabIndex={0} sx={{ display: "inline-flex", alignItems: "flex-start", gap: .5, cursor: "help",
                                               borderRadius: .5, "&:focus-visible": { outline: 2, outlineColor: "primary.main" } }}>
        {children}
        <InfoOutlined sx={{ fontSize: 15, color: "text.disabled", mt: "2px", flexShrink: 0 }} />
      </Box>
    </Tooltip>
  );
}

export function dicaAlgoritmo(id: string, a: InfoAlgoritmo | undefined) {
  if (!a) return <Explicacao titulo={id} linhas={[]} codigo={id} />;
  return <Explicacao titulo={a.nome} sub={a.ajuste} familia={a.familia} codigo={id}
                     linhas={[["Como funciona", a.o_que], ["Configuração", a.parametros]]} />;
}

/** Nome legível do algoritmo, a variação embaixo e a explicação no tooltip. */
export function NomeAlgoritmo({ id, cat, linha = false }: { id: string; cat: Catalogo | null; linha?: boolean }) {
  const a = cat?.algoritmos.find(x => x.id === id) || cat?.regressores?.find(x => x.id === id);
  return (
    <ComDica dica={dicaAlgoritmo(id, a)}>
      <Box component="span" sx={{ minWidth: 0 }}>
        <Typography component="span" variant="body2" fontWeight={550} sx={{ display: "block", lineHeight: 1.3 }}>
          {a ? a.nome : <Box component="span" sx={mono}>{id}</Box>}
          {linha && a && <Box component="span" sx={{ fontWeight: 400, color: "text.secondary" }}> · {a.ajuste}</Box>}
        </Typography>
        {!linha && a && <Typography component="span" variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.3 }}>
          {a.ajuste}</Typography>}
      </Box>
    </ComDica>
  );
}

export function NomeVariante({ id, cat }: { id: string | null; cat: Catalogo | null }) {
  if (!id) return <>—</>;
  const v: InfoVariante | undefined = cat?.variantes.find(x => x.id === id);
  return (
    <ComDica dica={<Explicacao titulo={v?.nome || id} codigo={id} linhas={[["O que entra no modelo", v?.o_que]]} />}>
      <Typography component="span" variant="body2" sx={{ lineHeight: 1.3 }}>{v?.nome || id}</Typography>
    </ComDica>
  );
}

/** Texto simples (sem tooltip), para títulos e mensagens. */
export function textoModelo(s: string | null | undefined, cat: Catalogo | null) {
  const { alg, variante } = separarModelo(s);
  const a = cat?.algoritmos.find(x => x.id === alg);
  const v = cat?.variantes.find(x => x.id === variante);
  return [a ? `${a.nome} — ${a.ajuste}` : alg, variante ? (v?.nome || variante) : null].filter(Boolean).join(" · ");
}
