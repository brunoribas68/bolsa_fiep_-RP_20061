import AutoGraphOutlined from "@mui/icons-material/AutoGraphOutlined";
import SaveOutlined from "@mui/icons-material/SaveOutlined";
import {
  Alert, Box, Button, Chip, CircularProgress, Link as MuiLink, MenuItem, Skeleton, Stack, Tab, Table, TableBody,
  TableCell, TableHead, TableRow, Tabs, TextField, Typography, useTheme,
} from "@mui/material";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAvisos } from "../componentes/avisos";
import { BarraProb, Cabecalho, ChipResultado, ChipRotulo, mono, Secao, SeloQC } from "../componentes/comum";
import GraficoCurvas, { type Serie } from "../componentes/GraficoCurvas";
import { data, num, pct } from "../formato";
import { SERIES } from "../tema";
import { NOME_CONJUNTO, NOME_ESTAGIO, type AmostraDetalhe as Det, type Curva, type PrevisaoAmostra, type PrevisaoReplica, type Protocolo } from "../tipos";
import { useCarregar } from "../usar";

function Edicao({ a, aoSalvar }: { a: Det; aoSalvar: (d: Det) => void }) {
  const avisar = useAvisos();
  const [f, setF] = useState({
    contamination_status: a.contamination_status === null ? "" : String(a.contamination_status),
    sample_log10_mean_cfu_ml: a.sample_log10_mean_cfu_ml === null ? "" : String(a.sample_log10_mean_cfu_ml),
    target_bacterium: a.target_bacterium || "", surface_type: a.surface_type || "",
    conjunto: a.conjunto || "", observacoes: a.observacoes || "",
  });
  const [salvando, setSalvando] = useState(false);
  const mudar = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  async function salvar() {
    setSalvando(true);
    const carga = f.sample_log10_mean_cfu_ml.trim().replace(",", ".");
    try {
      const d = await api.patch<Det>(`/api/amostras/${encodeURIComponent(a.sample_id)}`, {
        contamination_status: f.contamination_status === "" ? null : Number(f.contamination_status),
        sample_log10_mean_cfu_ml: carga === "" ? null : Number(carga),
        target_bacterium: f.target_bacterium, surface_type: f.surface_type,
        conjunto: f.conjunto || null, observacoes: f.observacoes,
      });
      aoSalvar(d); avisar("Alterações salvas.");
    } catch (e) { avisar((e as Error).message, "error"); } finally { setSalvando(false); }
  }
  return (
    <Stack spacing={2}>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(200px, 100%), 1fr))" }}>
        <TextField select label="Resultado do plaqueamento" value={f.contamination_status} onChange={mudar("contamination_status")}>
          <MenuItem value=""><em>Sem resultado</em></MenuItem><MenuItem value="1">Contaminada</MenuItem><MenuItem value="0">Não contaminada</MenuItem>
        </TextField>
        <TextField label="Carga (log₁₀ UFC/mL)" value={f.sample_log10_mean_cfu_ml} onChange={mudar("sample_log10_mean_cfu_ml")} inputProps={{ inputMode: "decimal" }} />
        <TextField label="Alvo / bactéria" value={f.target_bacterium} onChange={mudar("target_bacterium")} />
        <TextField label="Superfície" value={f.surface_type} onChange={mudar("surface_type")} placeholder="ex.: aço inox, esteira" />
        <TextField select label="Uso no treino" value={f.conjunto} onChange={mudar("conjunto")}>
          {Object.entries(NOME_CONJUNTO).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
        </TextField>
      </Box>
      <TextField label="Observações" multiline minRows={2} value={f.observacoes} onChange={mudar("observacoes")} inputProps={{ maxLength: 2000 }} />
      <Box><Button variant="contained" startIcon={<SaveOutlined />} onClick={salvar} disabled={salvando}>Salvar</Button></Box>
    </Stack>
  );
}

export default function AmostraDetalhe() {
  const { id = "" } = useParams();
  const { pode } = useAuth();
  const avisar = useAvisos();
  const tema = useTheme();
  const cores = SERIES[tema.palette.mode];
  const url = `/api/amostras/${encodeURIComponent(id)}`;
  const { dados: a, erro, setDados, recarregar } = useCarregar<Det>(url);
  const { dados: curvas } = useCarregar<Curva[]>(`${url}/curvas`);
  const { dados: protocolos } = useCarregar<Record<string, Protocolo>>("/api/protocolos");
  const [replica, setReplica] = useState<string | null>(null);
  const [prev, setPrev] = useState<{ amostra: PrevisaoAmostra | null; replicas: PrevisaoReplica[]; limiar: number } | null>(null);
  const [prevendo, setPrevendo] = useState(false);

  // protocolo da amostra: o que tem mais etapas em comum com as medições dela
  const etapas = useMemo(() => {
    const presentes = new Set((a?.medicoes || []).map(m => m.sensor_state));
    const melhor = Object.values(protocolos || {}).sort((x, y) => y.estagios.filter(e => presentes.has(e.id)).length
      - x.estagios.filter(e => presentes.has(e.id)).length)[0];
    return melhor ? melhor.estagios : [];
  }, [protocolos, a]);
  const ordem = etapas.map(e => e.id);
  const nomeEst = (s: string | null) => etapas.find(e => e.id === s)?.nome || NOME_ESTAGIO[s || ""] || s || "?";
  const eletrodos = useMemo(() => [...new Set((curvas || []).map(c => c.replicate_id || "—"))]
    .sort((x, y) => x.localeCompare(y, "pt-BR", { numeric: true })), [curvas]);
  const atual = replica ?? eletrodos[0] ?? null;
  const series: Serie[] = useMemo(() => (curvas || [])
    .filter(c => (c.replicate_id || "—") === atual)
    .sort((x, y) => ordem.indexOf(x.sensor_state || "") - ordem.indexOf(y.sensor_state || ""))
    .map(c => ({
      nome: `${nomeEst(c.sensor_state)}${c.qc_final && c.qc_final !== "PASS" ? ` (QC ${c.qc_final})` : ""}`,
      cor: cores[ordem.indexOf(c.sensor_state || "")] || tema.palette.text.secondary, x: c.potential_v, y: c.current_ua,
      fraca: !!c.qc_final && c.qc_final !== "PASS",
    })), [curvas, atual, etapas, cores]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function prever() {
    setPrevendo(true);
    try { setPrev(await api.post(`${url}/prever`)); recarregar(); }
    catch (e) { avisar((e as Error).message, "error"); } finally { setPrevendo(false); }
  }
  async function mudarEtapa(mid: string, sensor_state: string) {
    try { await api.patch(`/api/medicoes/${encodeURIComponent(mid)}`, { sensor_state }); recarregar(); avisar("Etapa alterada."); }
    catch (e) { avisar((e as Error).message, "error"); }
  }

  if (erro) return <Alert severity="error">{erro}</Alert>;
  if (!a) return <Skeleton variant="rounded" height={400} />;
  const medicoes = [...a.medicoes].sort((x, y) => String(x.replicate_id).localeCompare(String(y.replicate_id), "pt-BR", { numeric: true })
    || ordem.indexOf(x.sensor_state || "") - ordem.indexOf(y.sensor_state || ""));
  const historico = a.previsoes.filter(p => p.status === "amostra");
  return (
    <>
      <Cabecalho titulo={<Box component="span" sx={{ ...mono, fontSize: "inherit" }}>{a.sample_id}</Box>}
                 sub={<>{a.empresa || "Sem empresa"}
                   {a.coleta_id && <> · <MuiLink component={Link} to={`/coletas/${a.coleta_id}`}>coleta #{a.coleta_id}</MuiLink></>}
                   {a.atualizado_por && <> · editada por {a.atualizado_por} em {data(a.atualizado_em, true)}</>}</>}
                 acoes={<><ChipRotulo v={a.contamination_status} />
                   <Button variant="contained" onClick={prever} disabled={prevendo}
                           startIcon={prevendo ? <CircularProgress size={16} color="inherit" /> : <AutoGraphOutlined />}>
                     {prevendo ? "Calculando…" : "Prever com o modelo"}</Button></>} />
      <Stack spacing={2}>
        {prev?.amostra && (
          <Secao titulo="Previsão do modelo">
            <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems={{ md: "center" }}>
              <ChipResultado r={prev.amostra.resultado} size="medium" />
              <Box sx={{ width: 240 }}><BarraProb p={prev.amostra.prob_contaminada} limiar={prev.limiar} /></Box>
              <Typography>Nível: <b>{prev.amostra.nivel_contaminacao || "—"}</b></Typography>
              <Typography>Carga estimada: <b>{num(prev.amostra.log10_ufc_ml_estimado, 1)}</b> log₁₀ UFC/mL</Typography>
              <Typography color="text.secondary">{prev.amostra.replicas_avaliadas} de {prev.amostra.replicas_total} eletrodos · {pct(prev.amostra.concordancia)} concordam</Typography>
            </Stack>
            {prev.replicas.some(r => r.status !== "avaliada") && (
              <Alert severity="warning" sx={{ mt: 2 }}><Box component="ul" sx={{ m: 0, pl: 2 }}>
                {prev.replicas.filter(r => r.status !== "avaliada").map((r, i) => (
                  <li key={i}>Eletrodo {r.replicate_id || "?"}: {r.resultado.toLowerCase()} — {r.motivo}</li>))}
              </Box></Alert>)}
          </Secao>
        )}
        <Secao titulo="Voltamogramas">
          {eletrodos.length > 1 && (
            <Tabs value={atual} onChange={(_, v) => setReplica(v)} variant="scrollable" sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
              {eletrodos.map(r => <Tab key={r} value={r} label={`Eletrodo ${r}`} />)}
            </Tabs>)}
          {curvas ? <GraficoCurvas series={series} /> : <Skeleton variant="rounded" height={280} />}
        </Secao>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "minmax(0, 1fr)", lg: "minmax(0, 1.2fr) minmax(0, 1fr)" } }}>
          <Secao titulo="Dados da amostra">
            {pode("editar") ? <Edicao key={a.atualizado_em} a={a} aoSalvar={setDados} /> : (
              <Table size="small"><TableBody>
                {[["Carga", `${num(a.sample_log10_mean_cfu_ml, 2)} log₁₀ UFC/mL`], ["Alvo", a.target_bacterium || "—"],
                  ["Superfície", a.surface_type || "—"], ["Uso", NOME_CONJUNTO[a.conjunto || ""]], ["Observações", a.observacoes || "—"]]
                  .map(([k, v]) => <TableRow key={k}><TableCell sx={{ color: "text.secondary" }}>{k}</TableCell><TableCell>{v}</TableCell></TableRow>)}
              </TableBody></Table>)}
          </Secao>
          <Stack spacing={2}>
            <Secao titulo="Plaqueamento">
              {a.plaqueamentos.length ? (
                <Table size="small">
                  <TableHead><TableRow><TableCell>Placa</TableCell><TableCell align="right">Colônias</TableCell>
                    <TableCell align="right">UFC/mL</TableCell><TableCell align="right">log₁₀</TableCell></TableRow></TableHead>
                  <TableBody>{a.plaqueamentos.map(p => (
                    <TableRow key={p.replica}><TableCell>{p.replica}</TableCell><TableCell align="right">{num(p.colonias, 0)}</TableCell>
                      <TableCell align="right">{num(p.ufc_ml, 0)}</TableCell><TableCell align="right">{num(p.log10_ufc_ml, 2)}</TableCell></TableRow>))}
                  </TableBody>
                </Table>) : <Typography color="text.secondary">Sem placas registradas. O resultado pode ser informado em “Dados da amostra”.</Typography>}
            </Secao>
            <Secao titulo="Histórico de previsões">
              {historico.length ? (
                <Table size="small"><TableBody>
                  {historico.slice(0, 6).map((p, i) => (
                    <TableRow key={i}><TableCell sx={{ pl: 0 }}><ChipResultado r={p.resultado} /></TableCell>
                      <TableCell align="right">{pct(p.prob_contaminada)}</TableCell><TableCell>{p.nivel || ""}</TableCell>
                      <TableCell align="right" sx={{ color: "text.secondary", pr: 0 }}>{data(p.previsto_em, true)}</TableCell></TableRow>))}
                </TableBody></Table>) : <Typography color="text.secondary">Nenhuma previsão ainda.</Typography>}
            </Secao>
          </Stack>
        </Box>
        <Secao titulo={`Medições (${a.medicoes.length})`}>
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead><TableRow><TableCell>Eletrodo</TableCell><TableCell>Etapa do sensor</TableCell><TableCell>Técnica</TableCell>
                <TableCell>QC</TableCell><TableCell>Arquivo</TableCell><TableCell align="right">Pontos</TableCell></TableRow></TableHead>
              <TableBody>{medicoes.map(m => (
                <TableRow key={m.measurement_id} hover>
                  <TableCell>{m.replicate_id || "—"}</TableCell>
                  <TableCell>{pode("editar") ? (
                    <TextField select fullWidth={false} sx={{ minWidth: 170 }} value={m.sensor_state || ""}
                               inputProps={{ "aria-label": "Etapa do sensor" }} onChange={e => mudarEtapa(m.measurement_id, e.target.value)}>
                      {!m.sensor_state && <MenuItem value=""><em>definir</em></MenuItem>}
                      {etapas.map(s => <MenuItem key={s.id} value={s.id}>{s.nome}</MenuItem>)}
                    </TextField>) : nomeEst(m.sensor_state)}</TableCell>
                  <TableCell><Chip size="small" label={m.tecnica || "?"} variant="outlined" /></TableCell>
                  <TableCell><SeloQC v={m.qc_final} />
                    {m.qc_motivos && <Typography variant="caption" display="block" color="text.secondary">{m.qc_motivos}</Typography>}</TableCell>
                  <TableCell sx={mono}>{m.arquivo_origem}</TableCell><TableCell align="right">{m.n_pontos}</TableCell>
                </TableRow>))}
              </TableBody>
            </Table>
          </Box>
        </Secao>
      </Stack>
    </>
  );
}
