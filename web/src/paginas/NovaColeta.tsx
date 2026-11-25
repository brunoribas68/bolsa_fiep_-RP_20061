import SendIcon from "@mui/icons-material/Send";
import {
  Alert, AlertTitle, Box, Button, Card, CardContent, LinearProgress, MenuItem, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Cabecalho, ChipTipo, mono } from "../componentes/comum";
import Soltar, { type ArquivoComCaminho } from "../componentes/Soltar";
import type { Coleta, Empresa, Tipo } from "../tipos";
import { useCarregar } from "../usar";

/** O mesmo padrão que o servidor lê: técnica-etapa-concentração-eletrodo (dpv-branco-E1, dpv-RNA-0,1-E1). */
const PADRAO = /^(dpv|swv|cv)[-_ ]([a-z]+)(?:[-_ ](\d+(?:[.,]\d+)?))?[-_ ](E\d+)\b/i;

interface Previa { arquivo: ArquivoComCaminho; tipo: Tipo | null; conc: number | null; eletrodo: string | null; problema: string | null }

function previa(a: ArquivoComCaminho): Previa {
  const nome = a.arquivo.name.replace(/\.nox$/i, "");
  const m = PADRAO.exec(nome);
  const pasta = a.caminho.toLowerCase().split("/").slice(0, -1).map(p => p.replace(/[\s-]+/g, "_").replace("não", "nao"));
  const naPasta = [...pasta].reverse().find(p => p === "contaminado" || p === "nao_contaminado") || null;
  if (!/\.nox$/i.test(a.arquivo.name)) return { arquivo: a, tipo: null, conc: null, eletrodo: null, problema: "não é .nox" };
  if (!m) return { arquivo: a, tipo: null, conc: null, eletrodo: /E\d+/i.exec(nome)?.[0]?.toUpperCase() || null,
                   problema: "nome fora do padrão: o servidor tenta pelo procedimento do NOVA" };
  const etapa = m[2].toLowerCase();
  const tipo: Tipo | null = etapa === "branco" ? "branco" : etapa === "rna" ? "rna" : null;
  const antigo = tipo === "rna" && !!m[3] && !/[.,]/.test(m[3]);
  const conc = tipo === "rna" && m[3] && !antigo ? Number(m[3].replace(",", ".")) : null;
  let problema: string | null = null;
  if (!tipo) problema = `etapa "${etapa}" não entra na base (só branco e RNA)`;
  else if (naPasta === "contaminado" && tipo === "branco") problema = "branco dentro de contaminado/: não será gravado";
  else if (naPasta === "nao_contaminado" && tipo === "rna") problema = "RNA dentro de nao_contaminado/: não será gravado";
  else if (antigo) problema = "concentração sem vírgula (padrão antigo): o servidor usa a do procedimento do NOVA";
  else if (tipo === "rna" && !m[3]) problema = "sem concentração no nome: o servidor usa a do procedimento do NOVA";
  return { arquivo: a, tipo, conc, eletrodo: m[4].toUpperCase(), problema };
}

export default function NovaColeta() {
  const navegar = useNavigate();
  const { dados: empresas, recarregar } = useCarregar<Empresa[]>("/api/empresas");
  const [empresaId, setEmpresaId] = useState("");
  const [novaEmpresa, setNovaEmpresa] = useState("");
  const [dataColeta, setDataColeta] = useState(new Date().toISOString().slice(0, 10));
  const [descricao, setDescricao] = useState("");
  const [elemento, setElemento] = useState("");
  const [bacteria, setBacteria] = useState("");
  const [arquivos, setArquivos] = useState<ArquivoComCaminho[]>([]);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  const previas = useMemo(() => arquivos.map(previa), [arquivos]);
  const n = { branco: previas.filter(p => p.tipo === "branco" && !p.problema?.includes("não será")).length,
              rna: previas.filter(p => p.tipo === "rna" && !p.problema?.includes("não será")).length,
              fora: previas.filter(p => p.problema && (p.problema.includes("não será") || p.problema.includes("não entra") || p.problema.includes("não é"))).length };

  function receber(lista: ArquivoComCaminho[]) {
    setArquivos(atual => {
      const vistos = new Set(atual.map(a => a.caminho));
      return [...atual, ...lista.filter(a => !vistos.has(a.caminho))];
    });
  }

  async function enviar() {
    setErro(""); setEnviando(true);
    try {
      let emp = empresaId;
      if (empresaId === "nova") {
        emp = String((await api.post<Empresa>("/api/empresas", { nome: novaEmpresa.trim() })).id);
        recarregar();
      }
      const fd = new FormData();
      for (const a of arquivos) { fd.append("arquivos", a.arquivo, a.arquivo.name); fd.append("caminhos", a.caminho); }
      if (emp) fd.append("empresa_id", emp);
      if (descricao.trim()) fd.append("descricao", descricao.trim());
      if (dataColeta) fd.append("data_coleta", dataColeta);
      if (elemento.trim()) fd.append("elemento", elemento.trim());
      if (bacteria.trim()) fd.append("bacteria", bacteria.trim());
      const c = await api.post<Coleta>("/api/coletas", fd);
      navegar(`/coletas/${c.id}`, { state: { criada: true, importacao: c.importacao } });
    } catch (e) { setErro((e as Error).message); }
    finally { setEnviando(false); }
  }

  const podeEnviar = arquivos.length > 0 && (empresaId !== "nova" || novaEmpresa.trim()) && !enviando;
  return (
    <>
      <Cabecalho titulo="Nova coleta" sub="Envie os .nox de branco e de RNA. Cada arquivo vira um ensaio da base, com o pico já medido." />
      <Stack spacing={2}>
        <Card><CardContent>
          <Typography variant="h6" component="h2" sx={{ mb: 1.5 }}>1. De onde vêm os dados</Typography>
          <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))" }}>
            <TextField select label="Empresa ou laboratório" value={empresaId} onChange={e => setEmpresaId(e.target.value)}>
              <MenuItem value="">— sem empresa —</MenuItem>
              {empresas?.map(e => <MenuItem key={e.id} value={String(e.id)}>{e.nome}</MenuItem>)}
              <MenuItem value="nova"><i>+ cadastrar nova…</i></MenuItem>
            </TextField>
            {empresaId === "nova" && <TextField label="Nome da nova empresa" value={novaEmpresa} onChange={e => setNovaEmpresa(e.target.value)} />}
            <TextField label="Descrição" placeholder="ex.: Lote 3 — Oligo 4N" value={descricao} onChange={e => setDescricao(e.target.value)} />
            <TextField type="date" label="Data das medições" value={dataColeta} onChange={e => setDataColeta(e.target.value)}
                       InputLabelProps={{ shrink: true }} />
            <TextField label="Elemento de captura (se o NOVA não disser)" placeholder="ex.: Oligo 4N" value={elemento}
                       onChange={e => setElemento(e.target.value)} />
            <TextField label="Bactéria do RNA" placeholder="ex.: E. coli" value={bacteria} onChange={e => setBacteria(e.target.value)} />
          </Box>
        </CardContent></Card>

        <Card><CardContent>
          <Typography variant="h6" component="h2" sx={{ mb: .5 }}>2. Arquivos</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Nome no padrão da equipe: <Box component="span" sx={mono}>dpv-branco-E1.nox</Box> e{" "}
            <Box component="span" sx={mono}>dpv-RNA-0,1-E1.nox</Box> (concentração em ng/mL, sempre com vírgula; o mesmo
            E para o branco e o RNA do mesmo eletrodo). Pode arrastar a pasta com <Box component="span" sx={mono}>contaminado/</Box> e{" "}
            <Box component="span" sx={mono}>nao_contaminado/</Box>: arquivo na pasta errada não entra.
          </Typography>
          <Soltar aoReceber={receber} titulo="Arraste os .nox ou a pasta aqui" dica="ou use os botões abaixo" />
          {previas.length > 0 && (
            <>
              <Stack direction="row" spacing={2} sx={{ mt: 2, mb: 1 }} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="body2"><b>{n.branco}</b> branco · <b>{n.rna}</b> RNA
                  {n.fora > 0 && <Box component="span" sx={{ color: "warning.main" }}> · {n.fora} não entra(m)</Box>}</Typography>
                <Button size="small" onClick={() => setArquivos([])}>Limpar</Button>
              </Stack>
              <Box sx={{ overflowX: "auto", maxHeight: 360 }}>
                <Table size="small" stickyHeader>
                  <TableHead><TableRow><TableCell>Arquivo</TableCell><TableCell>Eletrodo</TableCell><TableCell>Será lido como</TableCell>
                    <TableCell>Observação</TableCell></TableRow></TableHead>
                  <TableBody>{previas.map(p => (
                    <TableRow key={p.arquivo.caminho}>
                      <TableCell sx={{ ...mono, whiteSpace: "nowrap" }}>{p.arquivo.caminho}</TableCell>
                      <TableCell>{p.eletrodo || "—"}</TableCell>
                      <TableCell><ChipTipo tipo={p.tipo} conc={p.conc} /></TableCell>
                      <TableCell sx={{ color: p.problema ? "warning.main" : "text.secondary" }}>{p.problema || "ok"}</TableCell>
                    </TableRow>))}
                  </TableBody>
                </Table>
              </Box>
            </>
          )}
        </CardContent></Card>

        {erro && <Alert severity="error"><AlertTitle>Não foi possível enviar</AlertTitle>{erro}</Alert>}
        {enviando && <LinearProgress />}
        <Stack direction="row" justifyContent="flex-end">
          <Button variant="contained" size="large" endIcon={<SendIcon />} disabled={!podeEnviar} onClick={enviar}>
            Enviar {arquivos.length || ""} arquivo(s)</Button>
        </Stack>
      </Stack>
    </>
  );
}
