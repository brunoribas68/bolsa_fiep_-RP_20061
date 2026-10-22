import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import ImageOutlined from "@mui/icons-material/ImageOutlined";
import SwapHoriz from "@mui/icons-material/SwapHoriz";
import {
  Alert, Box, Button, Chip, FormControlLabel, IconButton, LinearProgress, ListSubheader, MenuItem, Skeleton, Stack,
  Switch, TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography, useTheme,
} from "@mui/material";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cabecalho, Secao } from "../componentes/comum";
import { csv, svgParaPng, type Cabecalho as CabExport } from "../componentes/exportar";
import GraficoCurvas, { type Serie } from "../componentes/GraficoCurvas";
import GraficoDispersao, { ajuste, type Forma, type Grupo, type Ponto } from "../componentes/GraficoDispersao";
import { useAvisos } from "../componentes/avisos";
import { SERIES } from "../tema";
import { useCarregar } from "../usar";

type Valor = number | null;
interface Resumo { n: number; media: Valor[]; desvio: Valor[] }
interface Variavel { id: string; nome: string; unidade: string; grupo: string }
interface Dados {
  protocolos: Record<string, { nome: string; n_medicoes: number }>;
  protocolo: string | null; tecnica?: string; vazio: string | null;
  estagios?: { id: string; nome: string }[];
  classes?: { id: string; nome: string }[];
  n_medicoes?: number; n_reprovadas_qc?: number; n_eletrodos?: number;
  potencial_v?: number[];
  medias?: (Resumo & { estagio: string; classe: string })[];
  diferenca?: (Resumo & { classe: string })[];
  diferenca_nome?: string | null;
  individuais?: { estagio: string; classe: string; sample_id: string; replicate_id: string; y: Valor[] }[];
  individuais_diferenca?: { classe: string; y: Valor[] }[];
  pontos?: Record<string, (string | number | null | string[])[]>;
  variaveis?: Variavel[];
  empresas: { id: number; nome: string }[];
}

const CLASSES = ["contaminada", "nao_contaminada", "sem_rotulo"] as const;
const NOME_CLASSE: Record<string, string> = {
  contaminada: "Contaminada", nao_contaminada: "Não contaminada", sem_rotulo: "Sem resultado", todas: "Todas as amostras",
};
const FORMA_CLASSE: Record<string, Forma> = { contaminada: "circulo", nao_contaminada: "quadrado", sem_rotulo: "triangulo" };
const DIF = "__diferenca__";

const fmt = (v: number | null | undefined) =>
  v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toLocaleString("pt-BR", { maximumSignificantDigits: 4 });

export default function Graficos() {
  const tema = useTheme();
  const nav = useNavigate();
  const avisar = useAvisos();
  const cores = SERIES[tema.palette.mode];
  const cinza = tema.palette.mode === "light" ? "#8a919c" : "#7d8794";
  const corClasse: Record<string, string> = { contaminada: cores[1], nao_contaminada: cores[0], sem_rotulo: cinza };

  // filtros dos dados
  const [empresa, setEmpresa] = useState("");
  const [protocolo, setProtocolo] = useState("");
  const [todasQc, setTodasQc] = useState(false);
  const url = `/api/graficos?${new URLSearchParams({ ...(empresa && { empresa_id: empresa }), ...(protocolo && { protocolo }),
    qc: todasQc ? "todas" : "aprovadas" })}`;
  const { dados, erro, carregando } = useCarregar<Dados>(url);

  // gráfico de linha
  const [modo, setModo] = useState<"resultado" | "etapa">("resultado");
  const [etapa, setEtapa] = useState("");
  const [classe, setClasse] = useState("todas");
  const [faixa, setFaixa] = useState(true);
  const [indiv, setIndiv] = useState(false);
  const refLinha = useRef<SVGSVGElement>(null);

  // dispersão
  const [vx, setVx] = useState("");
  const [vy, setVy] = useState("");
  const [corPor, setCorPor] = useState<"resultado" | "empresa">("resultado");
  const [tendencia, setTendencia] = useState(true);
  const refDisp = useRef<SVGSVGElement>(null);

  const estagios = dados?.estagios || [];
  const ult = estagios[estagios.length - 1]?.id, ant = estagios[estagios.length - 2]?.id;
  const etapaAtual = etapa && (etapa === DIF ? dados?.diferenca_nome : estagios.some(e => e.id === etapa)) ? etapa
    : (dados?.diferenca_nome ? DIF : ult || "");
  const x = dados?.potencial_v || [];

  const seriesLinha: Serie[] = useMemo(() => {
    if (!dados?.medias) return [];
    const out: Serie[] = [];
    const comFaixa = (r: Resumo) => faixa ? {
      faixa: { inf: r.media.map((m, i) => m === null || r.desvio[i] === null ? null : m - (r.desvio[i] as number)),
               sup: r.media.map((m, i) => m === null || r.desvio[i] === null ? null : m + (r.desvio[i] as number)) },
    } : {};
    if (modo === "resultado") {
      if (indiv) {
        const fonte = etapaAtual === DIF ? dados.individuais_diferenca || []
          : (dados.individuais || []).filter(c => c.estagio === etapaAtual);
        fonte.forEach((c, i) => out.push({ nome: `i${i}`, cor: corClasse[c.classe], x, y: c.y, fundo: true }));
      }
      CLASSES.forEach(c => {
        const r = etapaAtual === DIF ? dados.diferenca?.find(d => d.classe === c)
          : dados.medias!.find(m => m.estagio === etapaAtual && m.classe === c);
        if (r) out.push({ nome: NOME_CLASSE[c], cor: corClasse[c], x, y: r.media, detalhe: `n = ${r.n}`, ...comFaixa(r) });
      });
    } else {
      if (indiv) {
        (dados.individuais || []).filter(c => classe === "todas" || c.classe === classe).forEach((c, i) =>
          out.push({ nome: `i${i}`, cor: cores[estagios.findIndex(e => e.id === c.estagio)] || cinza, x, y: c.y, fundo: true }));
      }
      estagios.forEach((e, i) => {
        const r = dados.medias!.find(m => m.estagio === e.id && m.classe === classe);
        if (r) out.push({ nome: e.nome, cor: cores[i] || cinza, x, y: r.media, detalhe: `n = ${r.n}`, ...comFaixa(r) });
      });
    }
    return out;
  }, [dados, modo, etapaAtual, classe, faixa, indiv, cores]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ----- dispersão
  const variaveis = dados?.variaveis || [];
  const temVar = (id?: string) => !!id && variaveis.some(v => v.id === id);
  const dIpico = ult && ant ? `delta_i_pico_${ult}_vs_${ant}` : "";
  const presets = [
    { nome: "Sinal × carga", x: dIpico, y: "log10_ufc_ml" },
    { nome: "Corrente de pico: etapa anterior × final", x: `${ant}_i_pico`, y: `${ult}_i_pico` },
    { nome: "Pico da etapa final: potencial × corrente", x: `${ult}_e_pico`, y: `${ult}_i_pico` },
    { nome: "Δ corrente × Δ área", x: dIpico, y: ult && ant ? `delta_area_${ult}_vs_${ant}` : "" },
  ].filter(p => temVar(p.x) && temVar(p.y));
  const vxAtual = temVar(vx) ? vx : presets[0]?.x || variaveis[0]?.id || "";
  const vyAtual = temVar(vy) ? vy : presets[0]?.y || variaveis[1]?.id || "";
  const nomeVar = (id: string) => {
    const v = variaveis.find(w => w.id === id);
    return v ? `${v.nome}${v.unidade && !v.nome.includes(v.unidade) ? ` (${v.unidade})` : ""}` : id;
  };

  const empresasTop = useMemo(() => {
    const ids = (dados?.pontos?.empresa_id || []) as (number | null)[];
    const cont = new Map<number, number>();
    ids.forEach(i => { if (i !== null) cont.set(i, (cont.get(i) || 0) + 1); });
    return [...cont.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([i]) => i);
  }, [dados]);
  const nomeEmpresa = (id: number | null) => dados?.empresas.find(e => e.id === id)?.nome || "(sem empresa)";

  const grupos: Grupo[] = corPor === "resultado"
    ? CLASSES.map(c => ({ id: c, nome: NOME_CLASSE[c], cor: corClasse[c], forma: FORMA_CLASSE[c] }))
    : [...empresasTop.map((id, i) => ({ id: String(id), nome: nomeEmpresa(id), cor: cores[i], forma: (["circulo", "quadrado", "triangulo"] as Forma[])[i] })),
       { id: "outras", nome: "Outras empresas", cor: cinza, forma: "losango" as Forma }];

  const linhasTabela = useMemo(() => {
    const p = dados?.pontos;
    if (!p) return [];
    const n = dados?.n_eletrodos || 0;
    return Array.from({ length: n }, (_, i) => Object.fromEntries(Object.entries(p).map(([k, v]) => [k, v[i]])) as Record<string, unknown>);
  }, [dados]);

  const pontos: Ponto[] = linhasTabela.flatMap(l => {
    const px = l[vxAtual] as number | null, py = l[vyAtual] as number | null;
    if (px === null || py === null || px === undefined || py === undefined) return [];
    const emp = l.empresa_id as number | null;
    const grupo = corPor === "resultado" ? String(l.classe) : emp !== null && empresasTop.includes(emp) ? String(emp) : "outras";
    return [{
      x: px, y: py, grupo, chave: `${l.sample_id}|${l.replicate_id}`,
      titulo: `${l.sample_id} · eletrodo ${l.replicate_id ?? "—"}`,
      linhas: [`${NOME_CLASSE[String(l.classe)]} · ${nomeEmpresa(emp)}`,
               `${nomeVar(vxAtual)}: ${fmt(px)}`, `${nomeVar(vyAtual)}: ${fmt(py)}`],
    }];
  });

  const porGrupo = variaveis.reduce<Record<string, Variavel[]>>((acc, v) => { (acc[v.grupo] ||= []).push(v); return acc; }, {});
  const opcoesVar = Object.entries(porGrupo).flatMap(([g, vs]) => [
    <ListSubheader key={`g${g}`}>{g}</ListSubheader>,
    ...vs.map(v => <MenuItem key={v.id} value={v.id}>{v.nome}</MenuItem>),
  ]);

  async function png(ref: React.RefObject<SVGSVGElement>, nome: string, cab: Omit<CabExport, "corTexto">) {
    try { if (ref.current) await svgParaPng(ref.current, nome, tema.palette.background.paper, { ...cab, corTexto: tema.palette.text.primary }); }
    catch (e) { avisar((e as Error).message, "error"); }
  }
  function baixarCsv() {
    const cols = [{ id: "sample_id", nome: "amostra" }, { id: "replicate_id", nome: "eletrodo" }, { id: "classe", nome: "resultado" },
                  { id: "empresa", nome: "empresa" }, ...variaveis.map(v => ({ id: v.id, nome: `${v.nome} [${v.unidade}]` }))];
    csv(linhasTabela.map(l => ({ ...l, classe: NOME_CLASSE[String(l.classe)], empresa: nomeEmpresa(l.empresa_id as number | null) })),
        cols, "descritores_por_eletrodo.csv");
  }

  const nomeEtapa = etapaAtual === DIF ? `Diferença ${dados?.diferenca_nome}` : estagios.find(e => e.id === etapaAtual)?.nome;
  const protos = Object.entries(dados?.protocolos || {});

  return (
    <>
      <Cabecalho titulo="Gráficos" sub="Voltamogramas e descritores dos dados do banco: compare contaminadas e não contaminadas, etapas e empresas." />

      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ md: "center" }} sx={{ mb: 2 }}>
        <TextField select label="Empresa" value={empresa} onChange={e => setEmpresa(e.target.value)} sx={{ maxWidth: { md: 260 } }}>
          <MenuItem value="">Todas</MenuItem>
          {(dados?.empresas || []).map(e => <MenuItem key={e.id} value={String(e.id)}>{e.nome}</MenuItem>)}
        </TextField>
        {protos.length > 1 && (
          <TextField select label="Protocolo" value={protocolo || dados?.protocolo || ""} onChange={e => setProtocolo(e.target.value)} sx={{ maxWidth: { md: 280 } }}>
            {protos.map(([k, p]) => <MenuItem key={k} value={k}>{p.nome} ({p.n_medicoes})</MenuItem>)}
          </TextField>
        )}
        <FormControlLabel control={<Switch checked={todasQc} onChange={e => setTodasQc(e.target.checked)} />}
                          label="Incluir medições reprovadas no QC" sx={{ flexShrink: 0 }} />
        <Box sx={{ flexGrow: 1 }} />
        {dados && !dados.vazio && (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={`${dados.tecnica} · ${protos.find(([k]) => k === dados.protocolo)?.[1].nome || dados.protocolo}`} />
            <Chip size="small" variant="outlined" label={`${dados.n_eletrodos} eletrodos`} />
            {!!dados.n_reprovadas_qc && <Chip size="small" variant="outlined" color={todasQc ? "warning" : "default"}
                                              label={`${dados.n_reprovadas_qc} reprovadas no QC${todasQc ? " (incluídas)" : " (fora)"}`} />}
          </Stack>
        )}
      </Stack>
      <Box sx={{ height: 4, mb: 1 }}>{carregando && <LinearProgress />}</Box>

      {erro && <Alert severity="error">{erro}</Alert>}
      {!dados && !erro && <Skeleton variant="rounded" height={420} />}
      {dados?.vazio && <Alert severity="info">{dados.vazio} Envie coletas em <b>Nova coleta</b> ou importe com <code>fiep db importar</code>.</Alert>}

      {dados && !dados.vazio && (
        <Stack spacing={2.5}>
          <Secao titulo="Voltamogramas (gráfico de linha)" acoes={
            <Tooltip title="Baixar PNG"><IconButton aria-label="Baixar o gráfico de linha como PNG" onClick={() => png(refLinha, `voltamogramas_${modo}`, {
              titulo: modo === "resultado" ? `Voltamograma médio por resultado — ${nomeEtapa}` : `Voltamograma médio por etapa — ${NOME_CLASSE[classe]}`,
              legenda: seriesLinha.filter(s => !s.fundo).map(s => ({ nome: `${s.nome}${s.detalhe ? ` (${s.detalhe})` : ""}`, cor: s.cor })),
            })}><ImageOutlined /></IconButton></Tooltip>
          }>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "center" }} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
              <ToggleButtonGroup size="small" exclusive value={modo} onChange={(_, v) => v && setModo(v)} aria-label="Comparar">
                <ToggleButton value="resultado">Por resultado</ToggleButton>
                <ToggleButton value="etapa">Por etapa</ToggleButton>
              </ToggleButtonGroup>
              {modo === "resultado" ? (
                <TextField select label="Etapa" value={etapaAtual} onChange={e => setEtapa(e.target.value)} sx={{ maxWidth: 300 }}>
                  {estagios.map(e => <MenuItem key={e.id} value={e.id}>{e.nome}</MenuItem>)}
                  {dados.diferenca_nome && <MenuItem value={DIF}>Diferença {dados.diferenca_nome}</MenuItem>}
                </TextField>
              ) : (
                <TextField select label="Amostras" value={classe} onChange={e => setClasse(e.target.value)} sx={{ maxWidth: 300 }}>
                  {["todas", ...CLASSES].map(c => <MenuItem key={c} value={c}>{NOME_CLASSE[c]}</MenuItem>)}
                </TextField>
              )}
              <FormControlLabel control={<Switch checked={faixa} onChange={e => setFaixa(e.target.checked)} />} label="Faixa ± 1 desvio padrão" />
              <FormControlLabel control={<Switch checked={indiv} onChange={e => setIndiv(e.target.checked)} />} label="Curvas individuais" />
            </Stack>
            <GraficoCurvas series={seriesLinha} svgRef={refLinha}
                           rotY={etapaAtual === DIF && modo === "resultado" ? `Δ corrente (µA)` : "Corrente (µA)"}
                           rotulo={modo === "resultado" ? `Voltamograma médio por resultado — ${nomeEtapa}` : `Voltamograma médio por etapa — ${NOME_CLASSE[classe]}`} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {modo === "resultado"
                ? <>Média das curvas de cada resultado do plaqueamento na etapa <b>{nomeEtapa}</b>
                    {etapaAtual === DIF && " (última etapa menos a anterior, no mesmo eletrodo — é o sinal que o modelo usa)"}.</>
                : <>Média de cada etapa do sensor ({NOME_CLASSE[classe].toLowerCase()}).</>}
              {" "}Curvas depois do QC e do mesmo pré-processamento do modelo (grade comum de potencial e suavização)
              {indiv && "; as linhas finas são eletrodos individuais (até 120)"}.
            </Typography>
          </Secao>

          <Secao titulo="Dispersão" acoes={
            <Stack direction="row" spacing={.5}>
              <Tooltip title="Baixar PNG"><IconButton aria-label="Baixar o gráfico de dispersão como PNG" onClick={() => png(refDisp, "dispersao", {
                titulo: `${nomeVar(vyAtual)} × ${nomeVar(vxAtual)}`,
                legenda: grupos.filter(g => pontos.some(p => p.grupo === g.id)).map(g => {
                  const doGrupo = pontos.filter(p => p.grupo === g.id), aj = tendencia ? ajuste(doGrupo) : null;
                  return { nome: `${g.nome} (n = ${doGrupo.length}${aj ? `, r = ${aj.r.toFixed(2).replace(".", ",")}` : ""})`, cor: g.cor };
                }),
              })}><ImageOutlined /></IconButton></Tooltip>
              <Tooltip title="Baixar a tabela (CSV, abre no Excel)"><IconButton aria-label="Baixar a tabela de descritores em CSV" onClick={baixarCsv}><DownloadOutlined /></IconButton></Tooltip>
            </Stack>
          }>
            {presets.length > 0 && (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                {presets.map(p => (
                  <Chip key={p.nome} label={p.nome} clickable variant={p.x === vxAtual && p.y === vyAtual ? "filled" : "outlined"}
                        color={p.x === vxAtual && p.y === vyAtual ? "primary" : "default"} onClick={() => { setVx(p.x); setVy(p.y); }} />
                ))}
              </Stack>
            )}
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} alignItems={{ md: "center" }} sx={{ mb: 2 }}>
              <TextField select label="Eixo X" value={vxAtual} onChange={e => setVx(e.target.value)}>{opcoesVar}</TextField>
              <Tooltip title="Trocar os eixos">
                <IconButton aria-label="Trocar os eixos X e Y" onClick={() => { setVx(vyAtual); setVy(vxAtual); }} sx={{ alignSelf: "center" }}><SwapHoriz /></IconButton>
              </Tooltip>
              <TextField select label="Eixo Y" value={vyAtual} onChange={e => setVy(e.target.value)}>{opcoesVar}</TextField>
              <TextField select label="Cor por" value={corPor} onChange={e => setCorPor(e.target.value as typeof corPor)} sx={{ maxWidth: { md: 180 } }}>
                <MenuItem value="resultado">Resultado</MenuItem>
                <MenuItem value="empresa">Empresa</MenuItem>
              </TextField>
              <FormControlLabel control={<Switch checked={tendencia} onChange={e => setTendencia(e.target.checked)} />}
                                label="Linha de tendência" sx={{ flexShrink: 0 }} />
            </Stack>
            <GraficoDispersao pontos={pontos} grupos={grupos} rotX={nomeVar(vxAtual)} rotY={nomeVar(vyAtual)} tendencia={tendencia}
                              svgRef={refDisp} aoClicar={p => nav(`/amostras/${encodeURIComponent(p.chave.split("|")[0])}`)} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Cada ponto é um eletrodo (amostra × réplica): {pontos.length} de {dados.n_eletrodos} têm as duas variáveis.
              Descritores calculados em cada etapa (corrente e potencial do pico, amplitude, área, largura) e as diferenças entre
              etapas; r = correlação de Pearson. Clique na legenda para ocultar um grupo e num ponto para abrir a amostra.
            </Typography>
            {corPor === "empresa" && empresasTop.length >= 3 && (dados.empresas.length > 3) && (
              <Typography variant="caption" color="text.disabled">As 3 empresas com mais eletrodos têm cor própria; as demais ficam em cinza.</Typography>
            )}
            <Box sx={{ mt: 1.5 }}>
              <Button size="small" startIcon={<DownloadOutlined />} onClick={baixarCsv}>Tabela completa dos descritores (CSV)</Button>
            </Box>
          </Secao>
        </Stack>
      )}
    </>
  );
}
