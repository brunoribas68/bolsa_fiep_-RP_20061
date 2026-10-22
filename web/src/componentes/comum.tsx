import { alpha, Alert, Box, Card, CardContent, Chip, LinearProgress, Stack, Typography, type ChipProps } from "@mui/material";
import type { ReactNode } from "react";
import { pct } from "../formato";

export function Cabecalho({ titulo, sub, acoes }: { titulo: ReactNode; sub?: ReactNode; acoes?: ReactNode }) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} justifyContent="space-between"
           alignItems={{ xs: "flex-start", sm: "flex-end" }} sx={{ mb: 3 }}>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h4" component="h1">{titulo}</Typography>
        {sub && <Typography color="text.secondary" sx={{ mt: .5 }}>{sub}</Typography>}
      </Box>
      {acoes && <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>{acoes}</Stack>}
    </Stack>
  );
}

export function Secao({ titulo, acoes, children, sx }: { titulo?: ReactNode; acoes?: ReactNode; children: ReactNode; sx?: object }) {
  return (
    <Card sx={sx}>
      <CardContent sx={{ p: { xs: 2, sm: 2.5 }, "&:last-child": { pb: { xs: 2, sm: 2.5 } } }}>
        {(titulo || acoes) && (
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }} spacing={1}>
            {titulo && <Typography variant="h6" component="h2">{titulo}</Typography>}
            {acoes}
          </Stack>
        )}
        {children}
      </CardContent>
    </Card>
  );
}

export function Kpi({ rotulo, valor, sub, cor }: { rotulo: string; valor: ReactNode; sub?: ReactNode; cor?: string }) {
  return (
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Typography variant="body2" color="text.secondary">{rotulo}</Typography>
        <Typography sx={{ fontSize: 30, fontWeight: 700, letterSpacing: "-.02em", fontVariantNumeric: "tabular-nums", color: cor }}>
          {valor}
        </Typography>
        {sub && <Typography variant="body2" color="text.secondary">{sub}</Typography>}
      </CardContent>
    </Card>
  );
}

const CHIP_RESULTADO: Record<string, { cor: ChipProps["color"]; texto: string }> = {
  "CONTAMINADA": { cor: "error", texto: "Contaminada" },
  "NÃO CONTAMINADA": { cor: "success", texto: "Não contaminada" },
  "REPETIR MEDIÇÃO": { cor: "warning", texto: "Repetir medição" },
  "SEM PREVISÃO": { cor: "default", texto: "Sem previsão" },
};

export function ChipResultado({ r, size = "small" }: { r: string | null | undefined; size?: ChipProps["size"] }) {
  if (!r) return <Typography color="text.secondary">—</Typography>;
  const c = CHIP_RESULTADO[r] || { cor: "default" as const, texto: r };
  return <Chip size={size} color={c.cor} variant={c.cor === "default" ? "outlined" : "filled"} label={c.texto}
               sx={c.cor !== "default" ? { bgcolor: t => alpha(t.palette[c.cor as "error"].main, .14), color: `${c.cor}.main` } : undefined} />;
}

export function ChipRotulo({ v }: { v: number | null }) {
  return <ChipResultado r={v === 1 ? "CONTAMINADA" : v === 0 ? "NÃO CONTAMINADA" : "SEM PREVISÃO"} />;
}

export function SeloQC({ v }: { v: string | null }) {
  const cor = v === "PASS" ? "success" : v === "FAIL" ? "error" : v === "REVIEW" ? "warning" : "default";
  return <Chip size="small" label={v || "—"} color={cor} variant="outlined" sx={{ height: 22, fontSize: 11.5 }} />;
}

export function BarraProb({ p, limiar }: { p: number | null; limiar: number }) {
  if (p === null || p === undefined) return <Typography color="text.secondary">—</Typography>;
  return (
    <Stack direction="row" alignItems="center" spacing={1} sx={{ minWidth: 150 }} title={`limiar ${pct(limiar)}`}>
      <Box sx={{ position: "relative", flex: 1 }}>
        <LinearProgress variant="determinate" value={p * 100} color={p >= limiar ? "error" : "success"}
                        sx={{ height: 7, borderRadius: 4 }} />
        <Box sx={{ position: "absolute", top: -4, left: `${limiar * 100}%`, width: 2, height: 15, bgcolor: "text.primary", borderRadius: 1 }} />
      </Box>
      <Typography variant="body2" sx={{ fontFamily: "monospace", minWidth: 38, textAlign: "right" }}>{pct(p)}</Typography>
    </Stack>
  );
}

export function Erro({ msg }: { msg: string }) {
  return msg ? <Alert severity="error" sx={{ mb: 2 }}>{msg}</Alert> : null;
}

export const mono = { fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace', fontSize: 13 };
