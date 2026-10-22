import { Box, Paper, Stack, Typography, useTheme } from "@mui/material";
import { useMemo, useRef, useState, type RefObject } from "react";
import { num } from "../formato";
import { useLargura } from "./largura";

export interface Serie {
  nome: string; cor: string; x: number[]; y: (number | null)[];
  fraca?: boolean;                                  // tracejada e clara (ex.: reprovada no QC)
  faixa?: { inf: (number | null)[]; sup: (number | null)[] };   // ex.: média ± desvio
  fundo?: boolean;                                  // curva de contexto: fina, sem legenda e sem dica
  detalhe?: string;                                 // texto extra na legenda (ex.: "n = 42")
}

const M = { e: 56, d: 14, t: 10, b: 38 };

export function ticks(min: number, max: number, n = 5) {
  const passo0 = (max - min) / n || 1;
  const pot = 10 ** Math.floor(Math.log10(passo0));
  const passo = [1, 2, 2.5, 5, 10].map(f => f * pot).find(p => p >= passo0) || passo0;
  const ini = Math.ceil(min / passo) * passo;
  const out: number[] = [];
  for (let v = ini; v <= max + 1e-12; v += passo) out.push(Number(v.toFixed(10)));
  return out;
}

/** Menor número de casas decimais que escreve todos os ticks sem arredondar (2,5 → 1 casa). */
export const casasTick = (arr: number[]) => {
  for (let c = 0; c <= 4; c++) if (arr.every(v => Math.abs(v * 10 ** c - Math.round(v * 10 ** c)) < 1e-6)) return c;
  return 4;
};

function maisProximo(xs: number[], alvo: number) {
  let melhor = 0, dist = Infinity;
  xs.forEach((x, i) => { const d = Math.abs(x - alvo); if (d < dist) { dist = d; melhor = i; } });
  return melhor;
}

const finito = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export default function GraficoCurvas({ series, rotX = "Potencial (V)", rotY = "Corrente (µA)", unidadeY = "µA", svgRef, rotulo }: {
  series: Serie[]; rotX?: string; rotY?: string; unidadeY?: string; svgRef?: RefObject<SVGSVGElement>; rotulo?: string;
}) {
  const proprio = useRef<SVGSVGElement>(null);
  const svg = svgRef || proprio;
  const t = useTheme();
  const [mx, setMx] = useState<number | null>(null);
  const [caixa, L] = useLargura<HTMLDivElement>();
  const A = Math.round(L < 520 ? L * .72 : 300);
  const principais = series.filter(s => !s.fundo);
  const nFundo = series.length - principais.length;
  const opFundo = Math.max(.07, Math.min(.3, 8 / Math.max(nFundo, 1)));

  const esc = useMemo(() => {
    const xs = series.flatMap(s => s.x);
    const ys = series.flatMap(s => [...s.y, ...(s.faixa ? [...s.faixa.inf, ...s.faixa.sup] : [])]).filter(finito);
    if (!xs.length || !ys.length) return null;
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = Math.min(...ys), y1 = Math.max(...ys);
    const folga = (y1 - y0) * 0.06 || 1;
    y0 -= folga; y1 += folga;
    const px = (v: number) => M.e + ((v - x0) / (x1 - x0 || 1)) * (L - M.e - M.d);
    const py = (v: number) => A - M.b - ((v - y0) / (y1 - y0 || 1)) * (A - M.t - M.b);
    return { x0, x1, y0, y1, px, py, inv: (p: number) => x0 + ((p - M.e) / (L - M.e - M.d)) * (x1 - x0) };
  }, [series, L, A]);

  if (!esc) return <Typography ref={caixa} color="text.secondary" sx={{ py: 4, textAlign: "center" }}>Sem curvas para mostrar.</Typography>;
  // quebra a linha onde não há valor (fora da faixa medida)
  const caminho = (x: number[], y: (number | null)[]) => {
    let d = "", novo = true;
    x.forEach((xi, i) => {
      const yi = y[i];
      if (!finito(yi)) { novo = true; return; }
      d += `${novo ? "M" : "L"}${esc.px(xi).toFixed(1)},${esc.py(yi).toFixed(1)}`;
      novo = false;
    });
    return d;
  };
  const area = (s: Serie) => {
    if (!s.faixa) return "";
    const idx = s.x.map((_, i) => i).filter(i => finito(s.faixa!.inf[i]) && finito(s.faixa!.sup[i]));
    if (idx.length < 2) return "";
    const ida = idx.map(i => `${esc.px(s.x[i]).toFixed(1)},${esc.py(s.faixa!.sup[i] as number).toFixed(1)}`);
    const volta = [...idx].reverse().map(i => `${esc.px(s.x[i]).toFixed(1)},${esc.py(s.faixa!.inf[i] as number).toFixed(1)}`);
    return `M${ida.join("L")}L${volta.join("L")}Z`;
  };
  const xAlvo = mx === null ? null : esc.inv(mx);
  const texto = { fill: t.palette.text.secondary, fontSize: 11 };
  const ty = ticks(esc.y0, esc.y1), tx = ticks(esc.x0, esc.x1, L < 520 ? 4 : 6);

  return (
    <Box ref={caixa} sx={{ position: "relative" }}>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        {principais.map(s => (
          <Stack key={s.nome} direction="row" spacing={.75} alignItems="center">
            <Box sx={{ width: 14, height: 3, borderRadius: 2, bgcolor: s.cor, opacity: s.fraca ? .4 : 1 }} />
            <Typography variant="body2" color="text.secondary">
              {s.nome}{s.detalhe && <Box component="span" sx={{ color: "text.disabled" }}> · {s.detalhe}</Box>}
            </Typography>
          </Stack>
        ))}
      </Stack>
      <svg ref={svg} viewBox={`0 0 ${L} ${A}`} role="img"
           aria-label={rotulo || `Gráfico de linha: ${principais.map(s => s.nome).join(", ")}`}
           style={{ display: "block", width: "100%", height: "auto", overflow: "visible" }}
           onMouseMove={e => {
             const r = svg.current!.getBoundingClientRect();
             const x = ((e.clientX - r.left) / r.width) * L;
             setMx(x >= M.e && x <= L - M.d ? x : null);
           }}
           onMouseLeave={() => setMx(null)}>
        <g>
          {ty.map(v => (
            <g key={`y${v}`}>
              <line x1={M.e} x2={L - M.d} y1={esc.py(v)} y2={esc.py(v)} stroke={t.palette.divider} />
              <text x={M.e - 8} y={esc.py(v) + 4} textAnchor="end" style={texto}>{num(v, casasTick(ty))}</text>
            </g>
          ))}
          {esc.y0 < 0 && esc.y1 > 0 && <line x1={M.e} x2={L - M.d} y1={esc.py(0)} y2={esc.py(0)} stroke={t.palette.text.disabled} />}
          {tx.map(v => (
            <text key={`x${v}`} x={esc.px(v)} y={A - M.b + 16} textAnchor="middle" style={texto}>{num(v, casasTick(tx))}</text>
          ))}
          <text x={(L + M.e) / 2} y={A - 4} textAnchor="middle" style={texto}>{rotX}</text>
          <text transform={`translate(13 ${(A - M.b) / 2}) rotate(-90)`} textAnchor="middle" style={texto}>{rotY}</text>
        </g>
        {series.filter(s => s.faixa).map(s => <path key={`f${s.nome}`} d={area(s)} fill={s.cor} opacity={.14} stroke="none" />)}
        {series.filter(s => s.fundo).map((s, i) => <path key={`b${i}`} d={caminho(s.x, s.y)} fill="none" stroke={s.cor}
                                                        strokeWidth={1} opacity={opFundo} />)}
        {principais.map(s => <path key={s.nome} d={caminho(s.x, s.y)} fill="none" stroke={s.cor} strokeWidth={2} strokeLinejoin="round"
                                   strokeDasharray={s.fraca ? "4 3" : undefined} opacity={s.fraca ? .4 : 1} />)}
        <g data-sem-exportar>
          {mx !== null && <line x1={mx} x2={mx} y1={M.t} y2={A - M.b} stroke={t.palette.text.secondary} strokeDasharray="3 3" />}
          {mx !== null && xAlvo !== null && principais.map(s => {
            const i = maisProximo(s.x, xAlvo);
            return finito(s.y[i]) ? <circle key={s.nome} cx={esc.px(s.x[i])} cy={esc.py(s.y[i] as number)} r={4} fill={s.cor}
                                            stroke={t.palette.background.paper} strokeWidth={2} /> : null;
          })}
        </g>
      </svg>
      {mx !== null && xAlvo !== null && principais.length > 0 && (
        <Paper variant="outlined" sx={{ position: "absolute", pointerEvents: "none", left: `min(${Math.min(mx / L * 100, 62)}%, calc(100% - 200px))`,
                                        top: 36, px: 1.5, py: 1, minWidth: 190, boxShadow: 3 }}>
          <Stack direction="row" justifyContent="space-between" spacing={2}>
            <Typography variant="body2" color="text.secondary">Potencial</Typography>
            <Typography variant="body2" fontFamily="monospace">{num(xAlvo, 3)} V</Typography>
          </Stack>
          {principais.map(s => {
            const i = maisProximo(s.x, xAlvo);
            const dp = s.faixa && finito(s.faixa.sup[i]) && finito(s.y[i]) ? (s.faixa.sup[i] as number) - (s.y[i] as number) : null;
            return (
              <Stack key={s.nome} direction="row" justifyContent="space-between" spacing={2}>
                <Stack direction="row" spacing={.75} alignItems="center">
                  <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: s.cor, flexShrink: 0 }} />
                  <Typography variant="body2" color="text.primary">{s.nome}</Typography>
                </Stack>
                <Typography variant="body2" fontFamily="monospace">
                  {num(s.y[i], 2)}{dp !== null && ` ± ${num(dp, 2)}`} {unidadeY}
                </Typography>
              </Stack>
            );
          })}
        </Paper>
      )}
    </Box>
  );
}
