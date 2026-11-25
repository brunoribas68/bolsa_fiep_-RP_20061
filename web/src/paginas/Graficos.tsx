import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import ImageOutlined from "@mui/icons-material/ImageOutlined";
import {
  Alert, Button, FormControlLabel, MenuItem, Skeleton, Stack, Switch, TextField, ToggleButton, ToggleButtonGroup,
  Typography, useTheme,
} from "@mui/material";
import { useMemo, useRef, useState } from "react";
import { useAvisos } from "../componentes/avisos";
import { Cabecalho, Secao } from "../componentes/comum";
import { csv, svgParaPng } from "../componentes/exportar";
import GraficoCurvas, { type Serie } from "../componentes/GraficoCurvas";
import GraficoDispersao, { ajuste, type Grupo, type Ponto } from "../componentes/GraficoDispersao";
import { concTexto, corEnsaio, num } from "../formato";
import type { Calibracao, Ensaio } from "../tipos";
import { useCarregar } from "../usar";

interface Curva { id: number; arquivo: string; eletrodo_id: string; tipo: "branco" | "rna"; concentracao: number; qc_flag: string | null; e: number[]; i: number[] }
interface Dados {
  curvas: Curva[]; pontos: (Ensaio & { i_base_ua: number | null; largura_v: number | null; area_uav: number | null })[];
  calibracao: Calibracao | null; empresas: { id: number; nome: string }[];
}

const VARIAVEIS = {
  log_conc: { nome: "log₁₀ concentração (ng/mL)", so_rna: true },
  queda_pct: { nome: "Queda do pico vs branco (%)", so_rna: true },
  altura_ua: { nome: "Altura do pico (µA)", so_rna: false },
  i_pico_ua: { nome: "Corrente do pico (µA)", so_rna: false },
  e_pico_v: { nome: "Potencial do pico (V)", so_rna: false },
  i_base_ua: { nome: "Corrente da base (µA)", so_rna: false },
  largura_v: { nome: "Largura a meia altura (V)", so_rna: false },
  area_uav: { nome: "Área (µA·V)", so_rna: false },
} as const;
type Var = keyof typeof VARIAVEIS;

/** Interpola y(x) em novos x (as curvas podem ter grades um pouco diferentes). */
function interp(x: number[], y: number[], alvo: number[]) {
  const ordem = x.map((_, k) => k).sort((a, b) => x[a] - x[b]);
  const xs = ordem.map(k => x[k]), ys = ordem.map(k => y[k]);
  let j = 0;
  return alvo.map(v => {
    if (v < xs[0] || v > xs[xs.length - 1]) return null;
    while (j < xs.length - 2 && xs[j + 1] < v) j++;
    const f = (v - xs[j]) / (xs[j + 1] - xs[j] || 1);
    return ys[j] + f * (ys[j + 1] - ys[j]);
  });
}

export default function Graficos() {
  const tema = useTheme();
  const avisar = useAvisos();
  const escuro = tema.palette.mode === "dark";
  const [empresa, setEmpresa] = useState("");
  const { dados, erro } = useCarregar<Dados>(`/api/graficos${empresa ? `?empresa_id=${empresa}` : ""}`);
  const [eletrodo, setEletrodo] = useState("");
  const [modo, setModo] = useState<"media" | "todas">("media");
  const [comFail, setComFail] = useState(false);
  const [vx, setVx] = useState<Var>("log_conc");
  const [vy, setVy] = useState<Var>("queda_pct");
  const refLinha = useRef<SVGSVGElement>(null);
  const refDisp = useRef<SVGSVGElement>(null);

  const curvas = useMemo(() => (dados?.curvas || []).filter(c => (comFail || c.qc_flag !== "FAIL") && (!eletrodo || c.eletrodo_id === eletrodo)),
                         [dados, comFail, eletrodo]);
  const concs = useMemo(() => [...new Set((dados?.curvas || []).map(c => c.concentracao))].sort((a, b) => a - b), [dados]);
  const eletrodos = useMemo(() => [...new Set((dados?.curvas || []).map(c => c.eletrodo_id))]
    .sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true })), [dados]);
  const cor = (c: { tipo: string; concentracao: number }) => corEnsaio(c.tipo, c.concentracao, concs, escuro);
  const nomeGrupo = (c: number) => (c === 0 ? "Branco" : `RNA ${concTexto(c)}`);

  const seriesLinha: Serie[] = useMemo(() => {
    if (!curvas.length) return [];
    if (modo === "todas" || eletrodo) {
      return curvas.map(c => ({ nome: `${c.arquivo}`, cor: cor(c), x: c.e, y: c.i, fraca: c.qc_flag === "FAIL" }));
    }
    const lo = Math.max(...curvas.map(c => Math.min(...c.e))), hi = Math.min(...curvas.map(c => Math.max(...c.e)));
    const grade = Array.from({ length: 150 }, (_, k) => lo + (hi - lo) * k / 149);
    const grupos = new Map<number, (number | null)[][]>();
    curvas.forEach(c => grupos.set(c.concentracao, [...(grupos.get(c.concentracao) || []), interp(c.e, c.i, grade)]));
    const fundo: Serie[] = curvas.map(c => ({ nome: `f${c.id}`, cor: cor(c), x: c.e, y: c.i, fundo: true }));
    const medias: Serie[] = [...grupos.entries()].sort((a, b) => a[0] - b[0]).map(([c, ys]) => {
      const m = grade.map((_, k) => { const v = ys.map(y => y[k]).filter((a): a is number => a !== null); return v.length ? v.reduce((s, a) => s + a, 0) / v.length : null; });
      const dp = grade.map((_, k) => {
        const v = ys.map(y => y[k]).filter((a): a is number => a !== null);
        if (v.length < 2 || m[k] === null) return null;
        return Math.sqrt(v.reduce((s, a) => s + (a - (m[k] as number)) ** 2, 0) / (v.length - 1));
      });
      return { nome: nomeGrupo(c), detalhe: `n = ${ys.length}`, cor: cor({ tipo: c === 0 ? "branco" : "rna", concentracao: c }), x: grade, y: m,
               faixa: ys.length > 1 ? { inf: m.map((v, k) => v === null || dp[k] === null ? null : v - (dp[k] as number)),
                                        sup: m.map((v, k) => v === null || dp[k] === null ? null : v + (dp[k] as number)) } : undefined };
    });
    return [...fundo, ...medias];
  }, [curvas, modo, eletrodo, concs, escuro]);  // eslint-disable-line react-hooks/exhaustive-deps

  const pontosBase = useMemo(() => (dados?.pontos || []).filter(p => (comFail || p.qc_flag !== "FAIL") && (!eletrodo || p.eletrodo_id === eletrodo)),
                             [dados, comFail, eletrodo]);
  const valor = (p: Dados["pontos"][number], v: Var): number | null =>
    v === "log_conc" ? (p.concentracao > 0 ? Math.log10(p.concentracao) : null) : (p[v] as number | null);
  const grupos: Grupo[] = concs.map(c => ({ id: String(c), nome: nomeGrupo(c), cor: cor({ tipo: c === 0 ? "branco" : "rna", concentracao: c }),
                                           forma: c === 0 ? "quadrado" : "circulo" }));
  const pontos: Ponto[] = pontosBase.flatMap(p => {
    const x = valor(p, vx), y = valor(p, vy);
    if (x === null || y === null || !Number.isFinite(x) || !Number.isFinite(y)) return [];
    return [{ x, y, grupo: String(p.concentracao), chave: String(p.id), titulo: p.arquivo || `ensaio ${p.id}`,
              linhas: [`eletrodo ${p.eletrodo_id}`, p.tipo === "rna" ? concTexto(p.concentracao) : "branco"] }];
  });
  const fora = pontosBase.length - pontos.length;
  const r = ajuste(pontos);

  async function png(ref: React.RefObject<SVGSVGElement>, nome: string, titulo: string, legenda: { nome: string; cor: string }[]) {
    try { if (ref.current) await svgParaPng(ref.current, nome, tema.palette.background.paper, { titulo, legenda, corTexto: tema.palette.text.primary }); }
    catch (e) { avisar((e as Error).message, "error"); }
  }
  const selVar = (rot: string, v: Var, set: (v: Var) => void) => (
    <TextField select size="small" label={rot} value={v} onChange={e => set(e.target.value as Var)} sx={{ minWidth: 230 }} fullWidth={false}>
      {Object.entries(VARIAVEIS).map(([k, d]) => <MenuItem key={k} value={k}>{d.nome}{d.so_rna ? " · só RNA" : ""}</MenuItem>)}
    </TextField>);

  return (
    <>
      <Cabecalho titulo="Gráficos" sub="As curvas de branco e de RNA e as medidas do pico de cada ensaio." />
      {erro && <Alert severity="error">{erro}</Alert>}
      {!dados ? <Skeleton variant="rounded" height={420} /> : !dados.curvas.length ? (
        <Alert severity="info">Ainda não há ensaios na base. Envie os .nox em Coletas → Nova coleta.</Alert>
      ) : (
        <Stack spacing={2}>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
            <TextField select size="small" label="Empresa" value={empresa} onChange={e => { setEmpresa(e.target.value); setEletrodo(""); }} sx={{ minWidth: 170 }} fullWidth={false}>
              <MenuItem value="">todas</MenuItem>
              {dados.empresas.map(e => <MenuItem key={e.id} value={String(e.id)}>{e.nome}</MenuItem>)}
            </TextField>
            <TextField select size="small" label="Eletrodo" value={eletrodo} onChange={e => setEletrodo(e.target.value)} sx={{ minWidth: 130 }} fullWidth={false}>
              <MenuItem value="">todos</MenuItem>
              {eletrodos.map(e => <MenuItem key={e} value={e}>{e}</MenuItem>)}
            </TextField>
            <FormControlLabel control={<Switch checked={comFail} onChange={e => setComFail(e.target.checked)} />} label="incluir reprovados no QC" />
          </Stack>

          <Secao titulo="Voltamogramas">
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
              {!eletrodo && <ToggleButtonGroup size="small" exclusive value={modo} onChange={(_, v) => v && setModo(v)}>
                <ToggleButton value="media">média por concentração</ToggleButton>
                <ToggleButton value="todas">todas as curvas</ToggleButton>
              </ToggleButtonGroup>}
              <Button size="small" startIcon={<ImageOutlined />} onClick={() => png(refLinha, "voltamogramas",
                eletrodo ? `Eletrodo ${eletrodo}` : "Voltamogramas DPV", grupos.map(g => ({ nome: g.nome, cor: g.cor })))}>PNG</Button>
            </Stack>
            <GraficoCurvas series={seriesLinha} svgRef={refLinha} rotY="δI (µA)" />
            <Typography variant="caption" color="text.secondary">
              {eletrodo || modo === "todas" ? "Cada linha é um arquivo; tracejada = reprovada no QC." :
                "Linha: média das curvas de cada concentração; faixa: ± 1 desvio-padrão; ao fundo, as curvas individuais."} Branco em cinza; RNA mais escuro quanto maior a concentração.
            </Typography>
          </Secao>

          <Secao titulo="Dispersão">
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
              {selVar("Eixo x", vx, setVx)}{selVar("Eixo y", vy, setVy)}
              <Button size="small" startIcon={<ImageOutlined />} onClick={() => png(refDisp, "dispersao",
                `${VARIAVEIS[vy].nome} × ${VARIAVEIS[vx].nome}`, grupos.map(g => ({ nome: g.nome, cor: g.cor })))}>PNG</Button>
              <Button size="small" startIcon={<DownloadOutlined />} onClick={() => csv(pontosBase as unknown as Record<string, unknown>[],
                [{ id: "arquivo", nome: "arquivo" }, { id: "eletrodo_id", nome: "eletrodo" }, { id: "tipo", nome: "tipo" },
                 { id: "concentracao", nome: "concentracao_ng_ml" }, ...Object.keys(VARIAVEIS).filter(k => k !== "log_conc").map(k => ({ id: k, nome: k }))],
                "picos.csv")}>CSV</Button>
            </Stack>
            <GraficoDispersao pontos={pontos} grupos={grupos} rotX={VARIAVEIS[vx].nome} rotY={VARIAVEIS[vy].nome} svgRef={refDisp} />
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {r ? `Reta: y = ${num(r.a, 3)} + ${num(r.b, 3)}·x · correlação r = ${num(r.r, 2)} (n = ${r.n}). ` : ""}
              {fora > 0 && `${fora} ensaio(s) fora do gráfico (branco não tem concentração nem queda; ou sem branco no eletrodo). `}
              {vx === "log_conc" && vy === "queda_pct" && dados.calibracao &&
                `Curva de calibração: ${num(dados.calibracao.inclinacao_pct_por_decada, 1)} % por década, R² ${num(dados.calibracao.r2, 2)}, LOD ${dados.calibracao.lod_ng_ml !== null ? `${num(dados.calibracao.lod_ng_ml, 3)} ng/mL` : `— (${dados.calibracao.lod_motivo})`}.`}
            </Typography>
          </Secao>
        </Stack>
      )}
    </>
  );
}
