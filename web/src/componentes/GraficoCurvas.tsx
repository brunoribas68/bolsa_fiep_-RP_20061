import { Box, Paper, Stack, Typography, useTheme } from "@mui/material";
import { useMemo, useRef, useState } from "react";
import { num } from "../formato";

export interface Serie { nome: string; cor: string; x: number[]; y: number[]; fraca?: boolean }

const L = 640, A = 300, M = { e: 56, d: 14, t: 10, b: 38 };

function ticks(min: number, max: number, n = 5) {
  const passo0 = (max - min) / n || 1;
  const pot = 10 ** Math.floor(Math.log10(passo0));
  const passo = [1, 2, 2.5, 5, 10].map(f => f * pot).find(p => p >= passo0) || passo0;
  const ini = Math.ceil(min / passo) * passo;
  const out: number[] = [];
  for (let v = ini; v <= max + 1e-12; v += passo) out.push(Number(v.toFixed(10)));
  return out;
}

function maisProximo(xs: number[], alvo: number) {
  let melhor = 0, dist = Infinity;
  xs.forEach((x, i) => { const d = Math.abs(x - alvo); if (d < dist) { dist = d; melhor = i; } });
  return melhor;
}

export default function GraficoCurvas({ series, rotX = "Potencial (V)", rotY = "Corrente (µA)" }: {
  series: Serie[]; rotX?: string; rotY?: string;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const t = useTheme();
  const [mx, setMx] = useState<number | null>(null);

  const esc = useMemo(() => {
    const xs = series.flatMap(s => s.x), ys = series.flatMap(s => s.y).filter(Number.isFinite);
    if (!xs.length || !ys.length) return null;
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = Math.min(...ys), y1 = Math.max(...ys);
    const folga = (y1 - y0) * 0.06 || 1;
    y0 -= folga; y1 += folga;
    const px = (v: number) => M.e + ((v - x0) / (x1 - x0 || 1)) * (L - M.e - M.d);
    const py = (v: number) => A - M.b - ((v - y0) / (y1 - y0 || 1)) * (A - M.t - M.b);
    return { x0, x1, y0, y1, px, py, inv: (p: number) => x0 + ((p - M.e) / (L - M.e - M.d)) * (x1 - x0) };
  }, [series]);

  if (!esc) return <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>Sem curvas para mostrar.</Typography>;
  const caminho = (s: Serie) => s.x.map((x, i) => `${i ? "L" : "M"}${esc.px(x).toFixed(1)},${esc.py(s.y[i]).toFixed(1)}`).join("");
  const xAlvo = mx === null ? null : esc.inv(mx);
  const texto = { fill: t.palette.text.secondary, fontSize: 11 };

  return (
    <Box sx={{ position: "relative" }}>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
        {series.map(s => (
          <Stack key={s.nome} direction="row" spacing={.75} alignItems="center">
            <Box sx={{ width: 14, height: 3, borderRadius: 2, bgcolor: s.cor, opacity: s.fraca ? .4 : 1 }} />
            <Typography variant="body2" color="text.secondary">{s.nome}</Typography>
          </Stack>
        ))}
      </Stack>
      <svg ref={svg} viewBox={`0 0 ${L} ${A}`} role="img" aria-label={`Voltamogramas: ${series.map(s => s.nome).join(", ")}`}
           style={{ display: "block", width: "100%", height: "auto", overflow: "visible" }}
           onMouseMove={e => {
             const r = svg.current!.getBoundingClientRect();
             const x = ((e.clientX - r.left) / r.width) * L;
             setMx(x >= M.e && x <= L - M.d ? x : null);
           }}
           onMouseLeave={() => setMx(null)}>
        <g>
          {ticks(esc.y0, esc.y1).map((v, _i, arr) => (
            <g key={`y${v}`}>
              <line x1={M.e} x2={L - M.d} y1={esc.py(v)} y2={esc.py(v)} stroke={t.palette.divider} />
              <text x={M.e - 8} y={esc.py(v) + 4} textAnchor="end" style={texto}>{num(v, arr.length > 1 && Math.abs(arr[1] - arr[0]) < 1 ? 1 : 0)}</text>
            </g>
          ))}
          {ticks(esc.x0, esc.x1, 6).map(v => (
            <text key={`x${v}`} x={esc.px(v)} y={A - M.b + 16} textAnchor="middle" style={texto}>{num(v, 2)}</text>
          ))}
          <text x={(L + M.e) / 2} y={A - 4} textAnchor="middle" style={texto}>{rotX}</text>
          <text transform={`translate(13 ${(A - M.b) / 2}) rotate(-90)`} textAnchor="middle" style={texto}>{rotY}</text>
        </g>
        {series.map(s => <path key={s.nome} d={caminho(s)} fill="none" stroke={s.cor} strokeWidth={2} strokeLinejoin="round"
                               strokeDasharray={s.fraca ? "4 3" : undefined} opacity={s.fraca ? .4 : 1} />)}
        {mx !== null && <line x1={mx} x2={mx} y1={M.t} y2={A - M.b} stroke={t.palette.text.secondary} strokeDasharray="3 3" />}
        {mx !== null && xAlvo !== null && series.map(s => {
          const i = maisProximo(s.x, xAlvo);
          return <circle key={s.nome} cx={esc.px(s.x[i])} cy={esc.py(s.y[i])} r={4} fill={s.cor}
                         stroke={t.palette.background.paper} strokeWidth={2} />;
        })}
      </svg>
      {mx !== null && xAlvo !== null && (
        <Paper variant="outlined" sx={{ position: "absolute", pointerEvents: "none", left: `${Math.min(mx / L * 100, 68)}%`,
                                        top: 36, px: 1.5, py: 1, minWidth: 180, boxShadow: 3 }}>
          <Stack direction="row" justifyContent="space-between" spacing={2}>
            <Typography variant="body2" color="text.secondary">Potencial</Typography>
            <Typography variant="body2" fontFamily="monospace">{num(xAlvo, 3)} V</Typography>
          </Stack>
          {series.map(s => {
            const i = maisProximo(s.x, xAlvo);
            return (
              <Stack key={s.nome} direction="row" justifyContent="space-between" spacing={2}>
                <Typography variant="body2" sx={{ color: s.cor, fontWeight: 600 }}>{s.nome}</Typography>
                <Typography variant="body2" fontFamily="monospace">{num(s.y[i], 2)} µA</Typography>
              </Stack>
            );
          })}
        </Paper>
      )}
    </Box>
  );
}
