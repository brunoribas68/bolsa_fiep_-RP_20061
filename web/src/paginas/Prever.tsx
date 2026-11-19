import DownloadOutlined from "@mui/icons-material/DownloadOutlined";
import PlayArrow from "@mui/icons-material/PlayArrow";
import {
  Alert, Box, Button, Checkbox, FormControlLabel, LinearProgress, Link as MuiLink, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, Tooltip, Typography, useTheme,
} from "@mui/material";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, baixar } from "../api";
import { useAvisos } from "../componentes/avisos";
import { BarraProb, Cabecalho, ChipResultado, ChipTipo, mono, Secao } from "../componentes/comum";
import { csv } from "../componentes/exportar";
import GraficoCurvas from "../componentes/GraficoCurvas";
import Soltar, { type ArquivoComCaminho } from "../componentes/Soltar";
import { num, pct } from "../formato";
import type { Modelo, ResultadoPrevisao } from "../tipos";
import { useCarregar } from "../usar";

interface Resposta { modelo: Modelo; resultados: ResultadoPrevisao[]; resumo: Record<string, number> }

export default function Prever() {
  const avisar = useAvisos();
  const t = useTheme();
  const { dados: modelo, erro: semModelo } = useCarregar<Modelo>("/api/modelo");
  const [arquivos, setArquivos] = useState<ArquivoComCaminho[]>([]);
  const [salvar, setSalvar] = useState(false);
  const [res, setRes] = useState<Resposta | null>(null);
  const [erro, setErro] = useState("");
  const [rodando, setRodando] = useState(false);

  function formulario() {
    const fd = new FormData();
    for (const a of arquivos) { fd.append("arquivos", a.arquivo, a.arquivo.name); fd.append("caminhos", a.caminho); }
    return fd;
  }
  async function prever() {
    setErro(""); setRodando(true);
    try {
      const fd = formulario();
      fd.append("salvar", String(salvar));
      setRes(await api.post<Resposta>("/api/prever", fd));
    } catch (e) { setErro((e as Error).message); }
    finally { setRodando(false); }
  }
  async function excel() {
    try { baixar(await api.post<Blob>("/api/excel", formulario()), "voltamogramas_excel.zip"); }
    catch (e) { avisar((e as Error).message, "error"); }
  }

  const cor = (r: string) => r === "CONTAMINADO" ? t.palette.error.main : r === "NÃO CONTAMINADO" ? t.palette.success.main : t.palette.warning.main;
  const series = (res?.resultados || []).filter(r => r.potential_v).map(r => ({
    nome: r.arquivo, cor: cor(r.resultado), x: r.potential_v!, y: r.current_ua!, fraca: r.resultado === "REPETIR MEDIÇÃO" }));
  return (
    <>
      <Cabecalho titulo="Previsão" sub="Classifica voltamogramas novos com o modelo em uso: contaminado (parece RNA) ou não contaminado (parece branco)." />
      <Stack spacing={2}>
        {semModelo ? <Alert severity="info">{semModelo} <MuiLink component={Link} to="/modelos">Ir para Modelos</MuiLink></Alert> : modelo && (
          <Alert severity={modelo.confiavel ? "success" : "warning"} icon={false}>
            Modelo em uso: <b>{modelo.algoritmo_nome}</b> · {modelo.representacao_nome} — acurácia balanceada {num(modelo.ab_referencia, 3)} ({modelo.referencia}),
            treinado com {modelo.dados.n_ensaios} curvas de {modelo.dados.n_eletrodos} eletrodo(s).
            {!modelo.confiavel && " Abaixo de 0,7: as previsões saem INCONCLUSIVO até haver mais dados."}
          </Alert>)}
        <Secao titulo="Arquivos">
          <Soltar aoReceber={l => setArquivos(a => [...a, ...l.filter(x => /\.nox$/i.test(x.arquivo.name))])}
                  titulo="Arraste os .nox aqui" dica="um ou vários; não entram na base" />
          {arquivos.length > 0 && (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
              <Typography variant="body2" sx={{ mr: 1 }}>{arquivos.length} arquivo(s)</Typography>
              <Button variant="contained" startIcon={<PlayArrow />} onClick={prever} disabled={rodando || !modelo}>Classificar</Button>
              <Button variant="outlined" startIcon={<DownloadOutlined />} onClick={excel}>Converter para Excel</Button>
              <Button onClick={() => { setArquivos([]); setRes(null); }}>Limpar</Button>
              <Tooltip title="Guarda o resultado de cada arquivo no histórico de previsões do banco.">
                <FormControlLabel control={<Checkbox checked={salvar} onChange={e => setSalvar(e.target.checked)} />} label="Registrar no banco" />
              </Tooltip>
            </Stack>)}
          {rodando && <LinearProgress sx={{ mt: 2 }} />}
          {erro && <Alert severity="error" sx={{ mt: 2 }}>{erro}</Alert>}
        </Secao>
        {res && (
          <>
            <Secao titulo="Resultado" acoes={<Button size="small" startIcon={<DownloadOutlined />} onClick={() => csv(
              res.resultados as unknown as Record<string, unknown>[],
              [{ id: "arquivo", nome: "arquivo" }, { id: "eletrodo_id", nome: "eletrodo" }, { id: "tipo_informado", nome: "nome_diz" },
               { id: "resultado", nome: "resultado" }, { id: "prob_contaminado", nome: "prob_contaminado" },
               { id: "e_pico_v", nome: "e_pico_v" }, { id: "i_pico_ua", nome: "i_pico_ua" }, { id: "altura_ua", nome: "altura_ua" },
               { id: "motivo", nome: "motivo" }], "previsao.csv")}>CSV</Button>}>
              <Box sx={{ overflowX: "auto" }}>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Arquivo</TableCell><TableCell>Eletrodo</TableCell>
                    <TableCell><Tooltip title="O que o nome do arquivo diz (dpv-branco / dpv-RNA). Serve para conferir o modelo."><span>Nome diz</span></Tooltip></TableCell>
                    <TableCell>Resultado</TableCell><TableCell>Probabilidade de contaminado</TableCell>
                    <TableCell align="right">Altura (µA)</TableCell></TableRow></TableHead>
                  <TableBody>{res.resultados.map(r => (
                    <TableRow key={r.arquivo + (r.sha256 || "")}>
                      <TableCell sx={{ ...mono, whiteSpace: "nowrap" }}>{r.arquivo}
                        {r.motivo && <Typography variant="caption" color="text.secondary" sx={{ display: "block", whiteSpace: "normal", fontFamily: "inherit" }}>{r.motivo}</Typography>}</TableCell>
                      <TableCell>{r.eletrodo_id || "—"}</TableCell>
                      <TableCell>{r.tipo_informado ? <ChipTipo tipo={r.tipo_informado} conc={r.concentracao_informada} /> : "—"}</TableCell>
                      <TableCell><ChipResultado r={r.resultado} /></TableCell>
                      <TableCell><BarraProb p={r.prob_contaminado} /></TableCell>
                      <TableCell align="right" sx={mono}>{num(r.altura_ua, 2)}</TableCell>
                    </TableRow>))}
                  </TableBody>
                </Table>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {Object.entries(res.resumo).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ")} · o traço na barra é o limiar ({pct(0.5)}).
              </Typography>
            </Secao>
            {series.length > 0 && <Secao titulo="Curvas"><GraficoCurvas series={series} rotY="δI (µA)" /></Secao>}
          </>
        )}
      </Stack>
    </>
  );
}
