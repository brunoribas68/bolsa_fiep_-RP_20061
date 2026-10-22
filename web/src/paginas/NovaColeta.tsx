import AddIcon from "@mui/icons-material/Add";
import DeleteOutline from "@mui/icons-material/DeleteOutline";
import InsertDriveFileOutlined from "@mui/icons-material/InsertDriveFileOutlined";
import SendIcon from "@mui/icons-material/Send";
import {
  Alert, AlertTitle, Box, Button, Card, CardContent, Chip, IconButton, InputAdornment, LinearProgress, MenuItem,
  Stack, Step, StepContent, StepLabel, Stepper, TextField, Tooltip, Typography,
} from "@mui/material";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Cabecalho } from "../componentes/comum";
import Soltar, { type ArquivoComCaminho } from "../componentes/Soltar";
import type { Coleta, Empresa } from "../tipos";
import { useCarregar } from "../usar";

interface AmostraForm { chave: number; codigo: string; rotulo: "" | "0" | "1"; carga: string; arquivos: ArquivoComCaminho[] }

let seq = 1;
const nova = (codigo = "", arquivos: ArquivoComCaminho[] = [], rotulo: AmostraForm["rotulo"] = ""): AmostraForm =>
  ({ chave: seq++, codigo, rotulo, carga: "", arquivos });
const CODIGO_OK = /^[\w.\-]{1,80}$/;

function rotuloDoCaminho(caminho: string): AmostraForm["rotulo"] {
  const c = caminho.toLowerCase();
  if (/n[aã]o[_\- ]?contaminad|negativ|control[e]?[_\- ]?neg/.test(c)) return "0";
  if (/contaminad|positiv/.test(c)) return "1";
  return "";
}

export default function NovaColeta() {
  const navegar = useNavigate();
  const { dados: empresas, recarregar } = useCarregar<Empresa[]>("/api/empresas");
  const [empresaId, setEmpresaId] = useState("");
  const [novaEmpresa, setNovaEmpresa] = useState("");
  const [dataColeta, setDataColeta] = useState(new Date().toISOString().slice(0, 10));
  const [descricao, setDescricao] = useState("");
  const [conjunto, setConjunto] = useState("");
  const [amostras, setAmostras] = useState<AmostraForm[]>([]);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  function receberLote(lista: ArquivoComCaminho[]) {
    const grupos = new Map<string, ArquivoComCaminho[]>();
    for (const a of lista) {
      const partes = a.caminho.split("/");
      const chave = partes.length >= 2 ? partes.slice(0, -1).join("/") : "";
      grupos.set(chave, [...(grupos.get(chave) || []), a]);
    }
    const novas = [...grupos.entries()].map(([pasta, arqs]) =>
      nova(pasta ? pasta.split("/").pop()! : "", arqs, rotuloDoCaminho(pasta)));
    setAmostras(atual => [...atual.filter(a => a.arquivos.length || a.codigo), ...novas]);
  }
  const alterar = (chave: number, mud: Partial<AmostraForm>) =>
    setAmostras(lista => lista.map(a => (a.chave === chave ? { ...a, ...mud } : a)));

  const problemas = (() => {
    const p: string[] = [];
    if (!amostras.length) p.push("Adicione pelo menos uma amostra com arquivos.");
    const codigos = amostras.map(a => a.codigo.trim());
    amostras.forEach((a, i) => {
      if (!a.codigo.trim()) p.push(`Amostra ${i + 1}: informe o código.`);
      else if (!CODIGO_OK.test(a.codigo.trim())) p.push(`Amostra ${a.codigo}: use só letras, números, ponto, hífen e _.`);
      if (!a.arquivos.length) p.push(`Amostra ${a.codigo || i + 1}: sem arquivos.`);
      if (a.carga && Number.isNaN(Number(a.carga.replace(",", ".")))) p.push(`Amostra ${a.codigo}: carga inválida.`);
    });
    const rep = codigos.filter((c, i) => c && codigos.indexOf(c) !== i);
    if (rep.length) p.push(`Códigos repetidos: ${[...new Set(rep)].join(", ")}.`);
    if (empresaId === "nova" && !novaEmpresa.trim()) p.push("Informe o nome da nova empresa.");
    return p;
  })();

  async function enviar() {
    setErro(""); setEnviando(true);
    try {
      let eid = empresaId;
      if (empresaId === "nova") {
        const e = await api.post<Empresa>("/api/empresas", { nome: novaEmpresa });
        eid = String(e.id); setEmpresaId(eid); recarregar();
      }
      const fd = new FormData();
      for (const a of amostras) for (const f of a.arquivos) {
        fd.append("arquivos", f.arquivo, f.arquivo.name);
        fd.append("caminhos", `${a.codigo.trim()}/${f.arquivo.name}`);
      }
      if (eid) fd.append("empresa_id", eid);
      if (descricao) fd.append("descricao", descricao);
      if (dataColeta) fd.append("data_coleta", dataColeta);
      if (conjunto) fd.append("conjunto", conjunto);
      fd.append("amostras", JSON.stringify(amostras.map(a => ({
        sample_id: a.codigo.trim(),
        contamination_status: a.rotulo === "" ? null : Number(a.rotulo),
        sample_log10_mean_cfu_ml: a.carga ? Number(a.carga.replace(",", ".")) : null,
      }))));
      const c = await api.post<Coleta>("/api/coletas", fd);
      navegar(`/coletas/${c.id}`, { state: { criada: true } });
    } catch (e) { setErro((e as Error).message); } finally { setEnviando(false); }
  }

  const total = amostras.reduce((n, a) => n + a.arquivos.length, 0);
  return (
    <>
      <Cabecalho titulo="Nova coleta"
                 sub="Envie os voltamogramas (.nox ou Excel/CSV exportado pelo NOVA) de cada amostra e o resultado do plaqueamento." />
      <Card><CardContent sx={{ p: { xs: 2, sm: 3 } }}>
        <Stepper orientation="vertical" nonLinear activeStep={-1}
                 sx={{ "& .MuiStepContent-root, & .MuiStepConnector-line": { borderColor: "divider" } }}>
          <Step active expanded>
            <StepLabel><Typography variant="h6">Dados da coleta</Typography></StepLabel>
            <StepContent>
              <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))", pt: 1 }}>
                <TextField select label="Empresa" value={empresaId} onChange={e => setEmpresaId(e.target.value)}>
                  <MenuItem value=""><em>Sem empresa</em></MenuItem>
                  {empresas?.map(e => <MenuItem key={e.id} value={String(e.id)}>{e.nome}</MenuItem>)}
                  <MenuItem value="nova"><AddIcon fontSize="small" sx={{ mr: 1 }} />Cadastrar nova empresa…</MenuItem>
                </TextField>
                {empresaId === "nova" && <TextField label="Nome da nova empresa" value={novaEmpresa} autoFocus
                                                    onChange={e => setNovaEmpresa(e.target.value)} inputProps={{ maxLength: 160 }} />}
                <TextField label="Data da coleta" type="date" value={dataColeta} onChange={e => setDataColeta(e.target.value)}
                           InputLabelProps={{ shrink: true }} />
                <TextField label="Descrição" value={descricao} onChange={e => setDescricao(e.target.value)}
                           placeholder="ex.: visita 2 — linha de envase" inputProps={{ maxLength: 300 }} />
                <TextField select label="Uso no treino" value={conjunto} onChange={e => setConjunto(e.target.value)}
                           helperText={conjunto === "teste" ? "Fica reservada para validação externa" : undefined}>
                  <MenuItem value="">Sorteio (50% treino · 25% validação · 25% teste)</MenuItem>
                  <MenuItem value="treino">Sempre no treino</MenuItem>
                  <MenuItem value="validacao">Sempre na validação</MenuItem>
                  <MenuItem value="teste">Reservar para teste (validação externa)</MenuItem>
                </TextField>
              </Box>
            </StepContent>
          </Step>
          <Step active expanded>
            <StepLabel><Typography variant="h6">Amostras e arquivos</Typography></StepLabel>
            <StepContent>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Cada eletrodo precisa das três etapas do sensor (ex.: bloqueio → mAb-NS1 → final, ou carbono → sonda → rRNA).
                Etapa e eletrodo são lidos dos nomes dos arquivos (ex.: <code>final-E3.nox</code>).
              </Typography>
              <Soltar aoReceber={receberLote} titulo="Arraste a pasta do lote aqui"
                      dica="Uma subpasta por amostra: o nome da pasta vira o código (pastas contaminada/ e nao_contaminada/ já preenchem o resultado)." />
              <Stack spacing={1.5} sx={{ mt: 2 }}>
                {amostras.map((a, i) => (
                  <Card key={a.chave} sx={{ bgcolor: "action.hover" }}>
                    <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
                      <Box sx={{ display: "grid", gap: 1.5, alignItems: "start",
                                 gridTemplateColumns: { xs: "minmax(0, 1fr)", sm: "minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, .8fr) auto" } }}>
                        <TextField label="Código da amostra" value={a.codigo} onChange={e => alterar(a.chave, { codigo: e.target.value })}
                                   placeholder={`ex.: EMP1-${String(i + 1).padStart(3, "0")}`}
                                   error={!!a.codigo && !CODIGO_OK.test(a.codigo.trim())} sx={{ bgcolor: "background.paper" }} />
                        <TextField select label="Resultado do plaqueamento" value={a.rotulo} sx={{ bgcolor: "background.paper" }}
                                   onChange={e => alterar(a.chave, { rotulo: e.target.value as AmostraForm["rotulo"] })}>
                          <MenuItem value=""><em>Ainda sem resultado</em></MenuItem>
                          <MenuItem value="1">Contaminada</MenuItem>
                          <MenuItem value="0">Não contaminada</MenuItem>
                        </TextField>
                        <TextField label="Carga" value={a.carga} placeholder="opcional" sx={{ bgcolor: "background.paper" }}
                                   onChange={e => alterar(a.chave, { carga: e.target.value })}
                                   InputProps={{ endAdornment: <InputAdornment position="end">log₁₀ UFC/mL</InputAdornment> }}
                                   inputProps={{ inputMode: "decimal" }} />
                        <Tooltip title="Remover amostra">
                          <IconButton onClick={() => setAmostras(l => l.filter(x => x.chave !== a.chave))} color="error"><DeleteOutline /></IconButton>
                        </Tooltip>
                      </Box>
                      <Box sx={{ mt: 1.5 }}>
                        <Soltar compacto pastas={false} titulo="Adicionar arquivos desta amostra"
                                aoReceber={l => alterar(a.chave, { arquivos: [...a.arquivos, ...l] })} />
                      </Box>
                      {a.arquivos.length > 0 && (
                        <Stack direction="row" spacing={.75} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
                          {a.arquivos.map((f, j) => (
                            <Chip key={j} size="small" icon={<InsertDriveFileOutlined />} label={f.arquivo.name}
                                  sx={{ fontFamily: "monospace", bgcolor: "background.paper" }}
                                  onDelete={() => alterar(a.chave, { arquivos: a.arquivos.filter((_, k) => k !== j) })} />
                          ))}
                        </Stack>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </Stack>
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }}>
                <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setAmostras(l => [...l, nova()])}>Adicionar amostra</Button>
                <Typography variant="body2" color="text.secondary">{amostras.length} amostra(s) · {total} arquivo(s)</Typography>
              </Stack>
            </StepContent>
          </Step>
          <Step active expanded>
            <StepLabel><Typography variant="h6">Enviar</Typography></StepLabel>
            <StepContent>
              {problemas.length > 0 && amostras.length > 0 && (
                <Alert severity="warning" sx={{ mb: 2 }}><AlertTitle>Antes de enviar</AlertTitle>
                  <Box component="ul" sx={{ m: 0, pl: 2 }}>{problemas.map(p => <li key={p}>{p}</li>)}</Box></Alert>
              )}
              {erro && <Alert severity="error" sx={{ mb: 2 }} role="alert">{erro}</Alert>}
              {enviando && <LinearProgress sx={{ mb: 2 }} />}
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }}>
                <Button variant="contained" size="large" endIcon={<SendIcon />} disabled={enviando || problemas.length > 0} onClick={enviar}>
                  {enviando ? "Enviando e processando…" : "Enviar coleta"}
                </Button>
                <Typography variant="body2" color="text.secondary">
                  Os arquivos são guardados, lidos, passam pelo controle de qualidade e vão para o banco.
                </Typography>
              </Stack>
            </StepContent>
          </Step>
        </Stepper>
      </CardContent></Card>
    </>
  );
}
