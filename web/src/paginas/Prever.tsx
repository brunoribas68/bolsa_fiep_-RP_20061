import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import InsertDriveFileOutlined from "@mui/icons-material/InsertDriveFileOutlined";
import PlayArrow from "@mui/icons-material/PlayArrow";
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, LinearProgress, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, Tooltip, Typography,
} from "@mui/material";
import ExpandMore from "@mui/icons-material/ExpandMore";
import { useState } from "react";
import { api, baixar } from "../api";
import { useAvisos } from "../componentes/avisos";
import { BarraProb, Cabecalho, ChipResultado, mono, Secao } from "../componentes/comum";
import Soltar, { type ArquivoComCaminho } from "../componentes/Soltar";
import { num, pct } from "../formato";
import { textoModelo, useCatalogo } from "../componentes/nomes";
import { csv } from "../componentes/exportar";
import type { Pico, PrevisaoAmostra, PrevisaoReplica } from "../tipos";

interface Resposta { modelo: string; algoritmo: string; limiar: number; amostras: PrevisaoAmostra[];
  resultados: PrevisaoReplica[]; avisos: string[]; picos?: Pico[];
  por_etapa?: Record<string, { algoritmo: string; teste_balanced_accuracy: number | null }> }

function ChipBase({ base }: { base?: string | null }) {
  if (!base) return <>—</>;
  const unica = base.startsWith("etapa única");
  return (
    <Tooltip title={unica
      ? "Faltam etapas do sensor neste eletrodo: a previsão usa o modelo treinado só com a etapa que existe. É menos confiável que a previsão com todas as etapas."
      : "Previsão com todas as etapas do sensor no mesmo eletrodo (o modelo principal)."}>
      <Chip size="small" variant="outlined" color={unica ? "warning" : "default"} label={unica ? base.replace("etapa única", "só uma etapa") : "todas as etapas"} />
    </Tooltip>
  );
}

const media = (v: (number | null | undefined)[]) => {
  const x = v.filter((a): a is number => typeof a === "number" && Number.isFinite(a));
  if (!x.length) return null;
  const m = x.reduce((s, a) => s + a, 0) / x.length;
  const dp = x.length > 1 ? Math.sqrt(x.reduce((s, a) => s + (a - m) ** 2, 0) / (x.length - 1)) : null;
  return { m, dp, cv: dp !== null && m ? Math.abs(dp / m) : null };
};

function TabelaPicos({ picos }: { picos: Pico[] }) {
  const pulso = picos.filter(p => (p.tecnica || "").toUpperCase() !== "CV");
  const cv = picos.filter(p => (p.tecnica || "").toUpperCase() === "CV");
  const ordem = (a: Pico, b: Pico) => String(a.sample_id).localeCompare(String(b.sample_id), "pt-BR") ||
    String(a.replicate_id).localeCompare(String(b.replicate_id), "pt-BR", { numeric: true });
  const linhaMedia = (lista: Pico[], cols: (keyof Pico)[], casas: number[], span: number) => (
    <TableRow sx={{ "& td": { fontWeight: 600, borderTop: 2, borderColor: "divider" } }}>
      <TableCell colSpan={span}>Média ± desvio ({lista.length})</TableCell>
      {cols.map((c, i) => {
        const r = media(lista.map(p => p[c] as number | null));
        return <TableCell key={String(c)} align="right">{r ? <>{num(r.m, casas[i])}{r.dp !== null && <Typography component="span" variant="caption" color="text.secondary"> ±{num(r.dp, casas[i])}</Typography>}</> : "—"}</TableCell>;
      })}
    </TableRow>
  );
  const id = (p: Pico) => (<>
    <TableCell sx={mono}>{p.sample_id || "—"}</TableCell><TableCell>{p.replicate_id || "—"}</TableCell>
    <TableCell>{p.etapa || p.sensor_state || "—"}</TableCell>
    <TableCell sx={{ ...mono, color: "text.secondary", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.arquivo || ""}>{(p.arquivo || "").split("/").pop()}</TableCell>
  </>);
  return (
    <Stack spacing={2.5}>
      {pulso.length > 0 && (
        <Box sx={{ overflowX: "auto" }}>
          <Typography variant="subtitle2" sx={{ mb: .5 }}>DPV / SWV — pico de corrente</Typography>
          <Table size="small">
            <TableHead><TableRow><TableCell>Amostra</TableCell><TableCell>Eletrodo</TableCell><TableCell>Etapa</TableCell><TableCell>Arquivo</TableCell>
              <TableCell align="right">E pico (V)</TableCell><TableCell align="right">I pico (µA)</TableCell><TableCell align="right">Base (µA)</TableCell>
              <TableCell align="right">Altura (µA)</TableCell><TableCell align="right">Largura ½ (V)</TableCell></TableRow></TableHead>
            <TableBody>
              {[...pulso].sort(ordem).map(p => (
                <TableRow key={p.measurement_id} hover>{id(p)}
                  <TableCell align="right">{num(p.e_pico_v, 3)}</TableCell><TableCell align="right">{num(p.i_pico_ua, 2)}</TableCell>
                  <TableCell align="right">{num(p.i_base_ua, 2)}</TableCell><TableCell align="right">{num(p.altura_ua, 2)}</TableCell>
                  <TableCell align="right">{num(p.largura_v, 3)}</TableCell></TableRow>))}
              {pulso.length > 1 && linhaMedia(pulso, ["e_pico_v", "i_pico_ua", "i_base_ua", "altura_ua", "largura_v"], [3, 2, 2, 2, 3], 4)}
            </TableBody>
          </Table>
        </Box>)}
      {cv.length > 0 && (
        <Box sx={{ overflowX: "auto" }}>
          <Typography variant="subtitle2" sx={{ mb: .5 }}>Voltametria cíclica — último ciclo</Typography>
          <Table size="small">
            <TableHead><TableRow><TableCell>Amostra</TableCell><TableCell>Eletrodo</TableCell><TableCell>Etapa</TableCell><TableCell>Arquivo</TableCell>
              <TableCell align="right">Epa (V)</TableCell><TableCell align="right">Ipa (µA)</TableCell><TableCell align="right">Epc (V)</TableCell>
              <TableCell align="right">Ipc (µA)</TableCell><TableCell align="right">ΔEp (V)</TableCell><TableCell align="right">E½ (V)</TableCell>
              <TableCell align="right">Ipa/|Ipc|</TableCell></TableRow></TableHead>
            <TableBody>
              {[...cv].sort(ordem).map(p => (
                <TableRow key={p.measurement_id} hover>{id(p)}
                  <TableCell align="right">{num(p.epa_v, 3)}</TableCell><TableCell align="right">{num(p.ipa_ua, 1)}</TableCell>
                  <TableCell align="right">{num(p.epc_v, 3)}</TableCell><TableCell align="right">{num(p.ipc_ua, 1)}</TableCell>
                  <TableCell align="right">{num(p.delta_ep_v, 3)}</TableCell><TableCell align="right">{num(p.e_meia_v, 3)}</TableCell>
                  <TableCell align="right">{num(p.razao_ipa_ipc, 2)}</TableCell></TableRow>))}
              {cv.length > 1 && linhaMedia(cv, ["epa_v", "ipa_ua", "epc_v", "ipc_ua", "delta_ep_v", "e_meia_v", "razao_ipa_ipc"], [3, 1, 3, 1, 3, 3, 2], 4)}
            </TableBody>
          </Table>
          <Typography variant="caption" color="text.secondary">
            ΔEp = Epa − Epc (perto de 0,059 V indica transferência de elétrons rápida); E½ = (Epa + Epc)/2; Ipa/|Ipc| perto de 1 indica processo reversível.
            A CV não entra no modelo (o protocolo usa {"DPV/SWV"}); serve para conferir o eletrodo.
          </Typography>
        </Box>)}
    </Stack>
  );
}

export default function Prever() {
  const avisar = useAvisos();
  const cat = useCatalogo();
  const [arquivos, setArquivos] = useState<ArquivoComCaminho[]>([]);
  const [res, setRes] = useState<Resposta | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const fd = () => {
    const f = new FormData();
    arquivos.forEach(a => { f.append("arquivos", a.arquivo, a.arquivo.name); f.append("caminhos", a.caminho); });
    return f;
  };
  async function analisar() {
    setOcupado(true);
    try { setRes(await api.post<Resposta>("/api/prever", fd())); }
    catch (e) { avisar((e as Error).message, "error"); } finally { setOcupado(false); }
  }
  async function excel() {
    try { baixar(await api.post<Blob>("/api/excel", fd()), "voltamogramas_excel.zip"); }
    catch (e) { avisar((e as Error).message, "error"); }
  }

  return (
    <>
      <Cabecalho titulo="Previsão rápida" sub="Classifica voltamogramas sem gravar no banco. Para guardar os dados, use Nova coleta." />
      <Stack spacing={2}>
        <Secao>
          <Soltar aoReceber={l => { setArquivos(a => [...a, ...l]); setRes(null); }} titulo="Arraste arquivos ou a pasta das amostras"
                  dica=".nox ou Excel/CSV do NOVA. Uma subpasta por amostra; sem pastas, o envio inteiro é uma amostra." />
          {arquivos.length > 0 && (
            <Stack direction="row" spacing={.75} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
              {arquivos.map((a, i) => <Chip key={i} size="small" icon={<InsertDriveFileOutlined />} label={a.caminho} sx={{ fontFamily: "monospace" }}
                                            onDelete={() => setArquivos(l => l.filter((_, j) => j !== i))} />)}
            </Stack>)}
          <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
            <Button variant="contained" startIcon={<PlayArrow />} disabled={!arquivos.length || ocupado} onClick={analisar}>
              {ocupado ? "Analisando…" : "Analisar"}</Button>
            <Button variant="outlined" startIcon={<DownloadOutlined />} disabled={!arquivos.some(a => /\.nox$/i.test(a.arquivo.name))}
                    onClick={excel}>Converter .nox para Excel</Button>
            {arquivos.length > 0 && <Button onClick={() => { setArquivos([]); setRes(null); }}>Limpar</Button>}
          </Stack>
          {ocupado && <LinearProgress sx={{ mt: 2 }} />}
        </Secao>
        {res && (
          <Secao titulo="Resultado por amostra">
            <Typography variant="body2" color="text.secondary" sx={{ mt: -1, mb: 1.5 }}>
              Modelo: {textoModelo(res.algoritmo, cat)} · o traço na barra é o limiar de decisão ({pct(res.limiar)}).
            </Typography>
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead><TableRow><TableCell>Amostra</TableCell><TableCell>Resultado</TableCell><TableCell>Prob. contaminada</TableCell>
                  <TableCell>Nível</TableCell><TableCell align="right">Carga (log₁₀ UFC/mL)</TableCell><TableCell>Eletrodos</TableCell><TableCell>Base da previsão</TableCell></TableRow></TableHead>
                <TableBody>{res.amostras.map(a => (
                  <TableRow key={a.sample_id}><TableCell sx={mono}>{a.sample_id}</TableCell><TableCell><ChipResultado r={a.resultado} /></TableCell>
                    <TableCell><BarraProb p={a.prob_contaminada} limiar={res.limiar} /></TableCell><TableCell>{a.nivel_contaminacao || "—"}</TableCell>
                    <TableCell align="right">{num(a.log10_ufc_ml_estimado, 1)}</TableCell>
                    <TableCell sx={{ color: "text.secondary" }}>{a.replicas_avaliadas} de {a.replicas_total} avaliados{a.concordancia !== null && ` · ${pct(a.concordancia)} concordam`}</TableCell>
                    <TableCell><ChipBase base={a.base} /></TableCell></TableRow>))}
                  {!res.amostras.length && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 3, color: "text.secondary" }}>Nenhuma amostra identificada.</TableCell></TableRow>}
                </TableBody>
              </Table>
            </Box>
            {res.amostras.some(a => a.base === "etapa única") && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                Algumas amostras foram previstas com <b>uma etapa só</b> do sensor (faltam as outras etapas no mesmo eletrodo).
                O resultado usa o modelo treinado só com aquela etapa e é menos confiável; veja a acurácia de cada etapa no detalhe por eletrodo.
                Para o resultado completo, meça todas as etapas.
              </Alert>)}
            <Accordion disableGutters variant="outlined" sx={{ mt: 2, "&:before": { display: "none" } }}>
              <AccordionSummary expandIcon={<ExpandMore />}><Typography>Detalhe por eletrodo</Typography></AccordionSummary>
              <AccordionDetails sx={{ overflowX: "auto" }}>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Amostra</TableCell><TableCell>Eletrodo</TableCell><TableCell>Resultado</TableCell>
                    <TableCell>Prob.</TableCell><TableCell>Base</TableCell><TableCell>Observação</TableCell></TableRow></TableHead>
                  <TableBody>{res.resultados.map((r, i) => (
                    <TableRow key={i}><TableCell sx={mono}>{r.sample_id || "—"}</TableCell><TableCell>{r.replicate_id || "—"}</TableCell>
                      <TableCell><ChipResultado r={r.resultado} /></TableCell><TableCell>{r.resultado === "INCONCLUSIVO" ? "—" : pct(r.prob_contaminada)}</TableCell>
                      <TableCell><ChipBase base={r.base} /></TableCell>
                      <TableCell sx={{ color: "text.secondary", minWidth: 280 }}>{r.motivo}</TableCell></TableRow>))}
                  </TableBody>
                </Table>
              </AccordionDetails>
            </Accordion>
            {res.avisos.length > 0 && <Alert severity="warning" sx={{ mt: 2 }}><Box component="ul" sx={{ m: 0, pl: 2 }}>
              {res.avisos.slice(0, 10).map(a => <li key={a}>{a}</li>)}</Box></Alert>}
          </Secao>
        )}
        {res && !!res.picos?.length && (
          <Secao titulo="Picos encontrados (potencial e corrente)" acoes={
            <Button size="small" startIcon={<DownloadOutlined />} onClick={() => csv(res.picos as unknown as Record<string, unknown>[], [
              { id: "sample_id", nome: "amostra" }, { id: "replicate_id", nome: "eletrodo" }, { id: "etapa", nome: "etapa" },
              { id: "tecnica", nome: "técnica" }, { id: "arquivo", nome: "arquivo" },
              { id: "e_pico_v", nome: "E pico (V)" }, { id: "i_pico_ua", nome: "I pico (µA)" }, { id: "i_base_ua", nome: "base (µA)" },
              { id: "altura_ua", nome: "altura (µA)" }, { id: "largura_v", nome: "largura meia altura (V)" },
              { id: "epa_v", nome: "Epa (V)" }, { id: "ipa_ua", nome: "Ipa (µA)" }, { id: "epc_v", nome: "Epc (V)" },
              { id: "ipc_ua", nome: "Ipc (µA)" }, { id: "delta_ep_v", nome: "ΔEp (V)" }, { id: "e_meia_v", nome: "E½ (V)" },
              { id: "razao_ipa_ipc", nome: "Ipa/|Ipc|" }], "picos.csv")}>CSV</Button>}>
            <Typography variant="body2" color="text.secondary" sx={{ mt: -1, mb: 1.5 }}>
              Lidos de cada arquivo, inclusive dos que o modelo não usa. O pico é o máximo local mais destacado, longe das pontas da varredura.
            </Typography>
            <TabelaPicos picos={res.picos} />
          </Secao>
        )}
      </Stack>
    </>
  );
}
