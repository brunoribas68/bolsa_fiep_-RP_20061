import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import InsertDriveFileOutlined from "@mui/icons-material/InsertDriveFileOutlined";
import PlayArrow from "@mui/icons-material/PlayArrow";
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, LinearProgress, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, Typography,
} from "@mui/material";
import ExpandMore from "@mui/icons-material/ExpandMore";
import { useState } from "react";
import { api, baixar } from "../api";
import { useAvisos } from "../componentes/avisos";
import { BarraProb, Cabecalho, ChipResultado, mono, Secao } from "../componentes/comum";
import Soltar, { type ArquivoComCaminho } from "../componentes/Soltar";
import { num, pct } from "../formato";
import type { PrevisaoAmostra, PrevisaoReplica } from "../tipos";

interface Resposta { modelo: string; algoritmo: string; limiar: number; amostras: PrevisaoAmostra[];
  resultados: PrevisaoReplica[]; avisos: string[] }

export default function Prever() {
  const avisar = useAvisos();
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
              Modelo {res.algoritmo} · o traço na barra é o limiar de decisão ({pct(res.limiar)}).
            </Typography>
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead><TableRow><TableCell>Amostra</TableCell><TableCell>Resultado</TableCell><TableCell>Prob. contaminada</TableCell>
                  <TableCell>Nível</TableCell><TableCell align="right">Carga (log₁₀ UFC/mL)</TableCell><TableCell>Eletrodos</TableCell></TableRow></TableHead>
                <TableBody>{res.amostras.map(a => (
                  <TableRow key={a.sample_id}><TableCell sx={mono}>{a.sample_id}</TableCell><TableCell><ChipResultado r={a.resultado} /></TableCell>
                    <TableCell><BarraProb p={a.prob_contaminada} limiar={res.limiar} /></TableCell><TableCell>{a.nivel_contaminacao || "—"}</TableCell>
                    <TableCell align="right">{num(a.log10_ufc_ml_estimado, 1)}</TableCell>
                    <TableCell sx={{ color: "text.secondary" }}>{a.replicas_avaliadas} de {a.replicas_total} avaliados{a.concordancia !== null && ` · ${pct(a.concordancia)} concordam`}</TableCell></TableRow>))}
                  {!res.amostras.length && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 3, color: "text.secondary" }}>Nenhuma amostra identificada.</TableCell></TableRow>}
                </TableBody>
              </Table>
            </Box>
            <Accordion disableGutters variant="outlined" sx={{ mt: 2, "&:before": { display: "none" } }}>
              <AccordionSummary expandIcon={<ExpandMore />}><Typography>Detalhe por eletrodo</Typography></AccordionSummary>
              <AccordionDetails sx={{ overflowX: "auto" }}>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Amostra</TableCell><TableCell>Eletrodo</TableCell><TableCell>Resultado</TableCell>
                    <TableCell>Prob.</TableCell><TableCell>Observação</TableCell></TableRow></TableHead>
                  <TableBody>{res.resultados.map((r, i) => (
                    <TableRow key={i}><TableCell sx={mono}>{r.sample_id || "—"}</TableCell><TableCell>{r.replicate_id || "—"}</TableCell>
                      <TableCell><ChipResultado r={r.resultado} /></TableCell><TableCell>{pct(r.prob_contaminada)}</TableCell>
                      <TableCell sx={{ color: "text.secondary" }}>{r.motivo}</TableCell></TableRow>))}
                  </TableBody>
                </Table>
              </AccordionDetails>
            </Accordion>
            {res.avisos.length > 0 && <Alert severity="warning" sx={{ mt: 2 }}><Box component="ul" sx={{ m: 0, pl: 2 }}>
              {res.avisos.slice(0, 10).map(a => <li key={a}>{a}</li>)}</Box></Alert>}
          </Secao>
        )}
      </Stack>
    </>
  );
}
