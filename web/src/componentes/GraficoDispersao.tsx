import { Box, ButtonBase, Paper, Stack, Typography, useTheme } from "@mui/material";
import { useMemo, useRef, useState, type RefObject } from "react";
import { num } from "../formato";
import { casasTick, ticks } from "./GraficoCurvas";
import { useLargura } from "./largura";

export type Forma = "circulo" | "quadrado" | "triangulo" | "losango";
export interface Grupo { id: string; nome: string; cor: string; forma: Forma }
export interface Ponto { x: number; y: number; grupo: string; titulo: string; linhas?: string[]; chave: string }

const M = { e: 60, d: 16, t: 12, b: 42 };

/** Regressão linear simples e correlação de Pearson. */
export function ajuste(pts: { x: number; y: number }[]) {
  const n = pts.length;
  if (n < 3) return null;
  const mx = pts.reduce((s, p) => s + p.x, 0) / n, my = pts.reduce((s, p) => s + p.y, 0) / n;
  let sxx = 0, syy = 0, sxy = 0;
  pts.forEach(p => { sxx += (p.x - mx) ** 2; syy += (p.y - my) ** 2; sxy += (p.x - mx) * (p.y - my); });
  if (!sxx || !syy) return null;
  const b = sxy / sxx;
  return { a: my - b * mx, b, r: sxy / Math.sqrt(sxx * syy), n };
}

function Marca({ forma, x, y, r, cor, borda, largura = 1.5 }: { forma: Forma; x: number; y: number; r: number; cor: string; borda: string; largura?: number }) {
  const comum = { fill: cor, stroke: borda, strokeWidth: largura };
  if (forma === "quadrado") return <rect x={x - r * .88} y={y - r * .88} width={r * 1.76} height={r * 1.76} rx={1.5} {...comum} />;
  if (forma === "triangulo") return <path d={`M${x},${y - r * 1.15}L${x + r * 1.05},${y + r * .75}L${x - r * 1.05},${y + r * .75}Z`} {...comum} />;
  if (forma === "losango") return <path d={`M${x},${y - r * 1.2}L${x + r * 1.2},${y}L${x},${y + r * 1.2}L${x - r * 1.2},${y}Z`} {...comum} />;
  return <circle cx={x} cy={y} r={r} {...comum} />;
}

export function IconeForma({ forma, cor }: { forma: Forma; cor: string }) {
  return (
    <svg width={12} height={12} viewBox="0 0 12 12" aria-hidden style={{ flexShrink: 0 }}>
      <Marca forma={forma} x={6} y={6.3} r={4.2} cor={cor} borda="none" largura={0} />
    </svg>
  );
}

export default function GraficoDispersao({ pontos, grupos, rotX, rotY, tendencia = true, aoClicar, svgRef, rotulo }: {
  pontos: Ponto[]; grupos: Grupo[]; rotX: string; rotY: string; tendencia?: boolean;
  aoClicar?: (p: Ponto) => void; svgRef?: RefObject<SVGSVGElement>; rotulo?: string;
}) {
  const t = useTheme();
  const proprio = useRef<SVGSVGElement>(null);
  const svg = svgRef || proprio;
  const [ocultos, setOcultos] = useState<Set<string>>(new Set());
  const [foco, setFoco] = useState<Ponto | null>(null);
  const [caixa, L] = useLargura<HTMLDivElement>();
  const A = Math.round(L < 520 ? L * .85 : 380);
  const visiveis = useMemo(() => pontos.filter(p => !ocultos.has(p.grupo)), [pontos, ocultos]);

  const esc = useMemo(() => {
    const base = visiveis.length ? visiveis : pontos;
    if (!base.length) return null;
    const xs = base.map(p => p.x), ys = base.map(p => p.y);
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const fx = (x1 - x0) * .05 || Math.abs(x0) * .1 || 1, fy = (y1 - y0) * .06 || Math.abs(y0) * .1 || 1;
    x0 -= fx; x1 += fx; y0 -= fy; y1 += fy;
    return {
      x0, x1, y0, y1,
      px: (v: number) => M.e + ((v - x0) / (x1 - x0)) * (L - M.e - M.d),
      py: (v: number) => A - M.b - ((v - y0) / (y1 - y0)) * (A - M.t - M.b),
    };
  }, [visiveis, pontos, L, A]);

  const ajustes = useMemo(() => Object.fromEntries(grupos.map(g => [g.id, ajuste(pontos.filter(p => p.grupo === g.id))])), [pontos, grupos]);
  const geral = useMemo(() => ajuste(visiveis), [visiveis]);

  if (!esc) return <Typography ref={caixa} color="text.secondary" sx={{ py: 6, textAlign: "center" }}>Sem pontos com as duas variáveis.</Typography>;
  const texto = { fill: t.palette.text.secondary, fontSize: 11 };
  const tx = ticks(esc.x0, esc.x1, L < 520 ? 4 : 6), ty = ticks(esc.y0, esc.y1, 6);
  const presentes = grupos.filter(g => pontos.some(p => p.grupo === g.id));

  function mover(e: React.MouseEvent) {
    const r = svg.current!.getBoundingClientRect();
    const mx = ((e.clientX - r.left) / r.width) * L, my = ((e.clientY - r.top) / r.height) * A;
    let melhor: Ponto | null = null, dist = 14 ** 2;          // alvo maior que a marca
    for (const p of visiveis) {
      const d = (esc!.px(p.x) - mx) ** 2 + (esc!.py(p.y) - my) ** 2;
      if (d < dist) { dist = d; melhor = p; }
    }
    setFoco(melhor);
  }

  const linhaTendencia = (aj: ReturnType<typeof ajuste>, cor: string, key: string, xs: number[]) => {
    if (!aj || xs.length < 3) return null;
    const a = Math.max(Math.min(...xs), esc.x0), b = Math.min(Math.max(...xs), esc.x1);
    return <line key={key} x1={esc.px(a)} x2={esc.px(b)} y1={esc.py(aj.a + aj.b * a)} y2={esc.py(aj.a + aj.b * b)}
                 stroke={cor} strokeWidth={2} strokeDasharray="6 4" opacity={.9} />;
  };

  return (
    <Box ref={caixa} sx={{ position: "relative" }}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }} role="group" aria-label="Legenda (clique para mostrar ou ocultar)">
        {presentes.map(g => {
          const aj = ajustes[g.id], n = pontos.filter(p => p.grupo === g.id).length, off = ocultos.has(g.id);
          return (
            <ButtonBase key={g.id} aria-pressed={!off} onClick={() => setOcultos(o => {
              const novo = new Set(o); if (novo.has(g.id)) novo.delete(g.id); else novo.add(g.id); return novo;
            })} sx={{ borderRadius: 1, px: .75, py: .25, opacity: off ? .45 : 1, "&:hover": { bgcolor: "action.hover" } }}>
              <Stack direction="row" spacing={.75} alignItems="center">
                <IconeForma forma={g.forma} cor={g.cor} />
                <Typography variant="body2" color="text.secondary" sx={{ textDecoration: off ? "line-through" : "none" }}>
                  {g.nome} <Box component="span" sx={{ color: "text.disabled" }}>· n = {n}{tendencia && aj ? ` · r = ${num(aj.r, 2)}` : ""}</Box>
                </Typography>
              </Stack>
            </ButtonBase>
          );
        })}
        {tendencia && geral && presentes.length > 1 && (
          <Typography variant="body2" color="text.disabled" sx={{ alignSelf: "center", px: .75 }}>todos: r = {num(geral.r, 2)}</Typography>
        )}
      </Stack>
      <svg ref={svg} viewBox={`0 0 ${L} ${A}`} role="img" aria-label={rotulo || `Gráfico de dispersão: ${rotY} por ${rotX}`}
           style={{ display: "block", width: "100%", height: "auto", overflow: "visible", cursor: foco && aoClicar ? "pointer" : "default" }}
           onMouseMove={mover} onMouseLeave={() => setFoco(null)} onClick={() => foco && aoClicar?.(foco)}>
        <g>
          {ty.map(v => (
            <g key={`y${v}`}>
              <line x1={M.e} x2={L - M.d} y1={esc.py(v)} y2={esc.py(v)} stroke={t.palette.divider} />
              <text x={M.e - 8} y={esc.py(v) + 4} textAnchor="end" style={texto}>{num(v, casasTick(ty))}</text>
            </g>
          ))}
          {tx.map(v => (
            <g key={`x${v}`}>
              <line x1={esc.px(v)} x2={esc.px(v)} y1={M.t} y2={A - M.b} stroke={t.palette.divider} opacity={.6} />
              <text x={esc.px(v)} y={A - M.b + 16} textAnchor="middle" style={texto}>{num(v, casasTick(tx))}</text>
            </g>
          ))}
          <text x={(L + M.e) / 2} y={A - 6} textAnchor="middle" style={texto}>{rotX}</text>
          <text transform={`translate(13 ${(A - M.b) / 2}) rotate(-90)`} textAnchor="middle" style={texto}>{rotY}</text>
        </g>
        {visiveis.map(p => {
          const g = grupos.find(x => x.id === p.grupo)!;
          return <Marca key={p.chave} forma={g.forma} x={esc.px(p.x)} y={esc.py(p.y)} r={4.2} cor={g.cor}
                        borda={t.palette.background.paper} />;
        })}
        <defs><clipPath id="area-dispersao"><rect x={M.e} y={M.t} width={L - M.e - M.d} height={A - M.t - M.b} /></clipPath></defs>
        <g clipPath="url(#area-dispersao)">
          {tendencia && presentes.filter(g => !ocultos.has(g.id)).map(g =>
            linhaTendencia(ajustes[g.id], g.cor, `t${g.id}`, pontos.filter(p => p.grupo === g.id).map(p => p.x)))}
        </g>
        <g data-sem-exportar>
          {foco && (() => {
            const g = grupos.find(x => x.id === foco.grupo)!;
            return <Marca forma={g.forma} x={esc.px(foco.x)} y={esc.py(foco.y)} r={7} cor={g.cor} borda={t.palette.text.primary} largura={2} />;
          })()}
        </g>
      </svg>
      {foco && (
        <Paper variant="outlined" sx={{
          position: "absolute", pointerEvents: "none", boxShadow: 3, px: 1.5, py: 1, minWidth: 180,
          left: `min(${Math.min(esc.px(foco.x) / L * 100 + 2, 64)}%, calc(100% - 200px))`, top: `${Math.min(esc.py(foco.y) / A * 100, 70)}%`,
        }}>
          <Typography variant="subtitle2">{foco.titulo}</Typography>
          {foco.linhas?.map(l => <Typography key={l} variant="body2" color="text.secondary">{l}</Typography>)}
          {aoClicar && <Typography variant="caption" color="text.disabled">clique para abrir a amostra</Typography>}
        </Paper>
      )}
    </Box>
  );
}
