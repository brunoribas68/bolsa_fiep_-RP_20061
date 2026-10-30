import CheckCircleOutline from "@mui/icons-material/CheckCircleOutline";
import PlayArrow from "@mui/icons-material/PlayArrow";
import StarOutline from "@mui/icons-material/StarOutline";
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider,
  FormControlLabel, FormGroup, LinearProgress, Link as MuiLink, MenuItem, Skeleton, Stack, Switch, Tab, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, TextField, Tooltip, Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAvisos } from "../componentes/avisos";
import { Cabecalho, Kpi, mono, Secao } from "../componentes/comum";
import Confirmar from "../componentes/Confirmar";
import { ComDica, dicaAlgoritmo, NomeAlgoritmo, NomeVariante, separarModelo, textoModelo, useCatalogo } from "../componentes/nomes";
import { data, num, pct } from "../formato";
import type { Catalogo, Empresa, LinhaComparacao, ModeloDetalhe, ModeloResumo, Treino } from "../tipos";
import { useCarregar } from "../usar";

function barra(v: number | null | undefined, melhor = false) {
  if (v === null || v === undefined) return <Typography variant="body2" color="text.secondary">—</Typography>;
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 120, color: "text.disabled" }}>
      <LinearProgress variant="determinate" value={Math.max(0, (v - 0.5) / 0.5) * 100} sx={{ flex: 1, height: 6, borderRadius: 3 }}
                      color={melhor ? "primary" : "inherit"} />
      <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", minWidth: 40, textAlign: "right", fontWeight: melhor ? 700 : 400 }}>
        {num(v, 3)}</Typography>
    </Stack>
  );
}

// ------------------------------------------------------------------ novo treino
function NovoTreino({ aberto, aoFechar, aoIniciar }: { aberto: boolean; aoFechar: () => void; aoIniciar: (t: Treino) => void }) {
  const { pode } = useAuth();
  const avisar = useAvisos();
  const cat = useCatalogo();
  const { dados: empresas } = useCarregar<Empresa[]>(aberto ? "/api/empresas" : null);
  const [algs, setAlgs] = useState<string[]>([]);
  const [vars, setVars] = useState<string[]>([]);
  const [emps, setEmps] = useState<string[]>([]);
  const [comExemplo, setComExemplo] = useState(false);
  const [ativar, setAtivar] = useState(false);
  const [prop, setProp] = useState({ treino: 50, validacao: 25, teste: 25 });
  useEffect(() => { if (cat) { setAlgs(cat.algoritmos.map(a => a.id)); setVars(cat.variantes.map(v => v.id)); } }, [cat]);

  const familias = useMemo(() => {
    const m = new Map<string, Catalogo["algoritmos"]>();
    (cat?.algoritmos || []).forEach(a => m.set(a.familia, [...(m.get(a.familia) || []), a]));
    return [...m.entries()];
  }, [cat]);
  const alternar = (lista: string[], set: (l: string[]) => void, id: string) =>
    set(lista.includes(id) ? lista.filter(x => x !== id) : [...lista, id]);
  const somaOk = prop.treino + prop.validacao + prop.teste === 100;

  async function iniciar() {
    try {
      const t = await api.post<Treino>("/api/treinos", {
        algoritmos: algs, variantes: vars, empresas: emps.map(Number), com_exemplo: comExemplo, ativar,
        treino: prop.treino / 100, validacao: prop.validacao / 100, teste: prop.teste / 100,
      });
      avisar("Treino iniciado."); aoIniciar(t); aoFechar();
    } catch (e) { avisar((e as Error).message, "error"); }
  }

  return (
    <Dialog open={aberto} onClose={aoFechar} fullWidth maxWidth="md">
      <DialogTitle>Treinar e comparar modelos</DialogTitle>
      <DialogContent dividers>
        {!cat ? <Skeleton variant="rounded" height={300} /> : (
          <Stack spacing={3}>
            <Box>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="subtitle2">Algoritmos ({algs.length} de {cat.algoritmos.length})</Typography>
                <Stack direction="row" spacing={1}>
                  <Button size="small" onClick={() => setAlgs(cat.algoritmos.map(a => a.id))}>todos</Button>
                  <Button size="small" onClick={() => setAlgs([])}>nenhum</Button>
                </Stack>
              </Stack>
              <Box sx={{ display: "grid", gap: 1.5, mt: 1, gridTemplateColumns: "repeat(auto-fit, minmax(min(250px, 100%), 1fr))" }}>
                {familias.map(([fam, lista]) => (
                  <Card key={fam} sx={{ bgcolor: "action.hover" }}><CardContent sx={{ py: 1.25, "&:last-child": { pb: 1.25 } }}>
                    <Typography variant="overline" color="text.secondary">{fam}</Typography>
                    <FormGroup>
                      {lista.map(a => (
                        <FormControlLabel key={a.id} sx={{ alignItems: "flex-start", my: .25, "& .MuiCheckbox-root": { pt: .25 } }}
                                          control={<Checkbox size="small" checked={algs.includes(a.id)} onChange={() => alternar(algs, setAlgs, a.id)} />}
                                          label={<NomeAlgoritmo id={a.id} cat={cat} />} />))}
                    </FormGroup>
                  </CardContent></Card>))}
              </Box>
            </Box>
            <Box>
              <Typography variant="subtitle2">Representações da curva ({vars.length} de {cat.variantes.length})</Typography>
              <Typography variant="caption" color="text.secondary">O que do voltamograma entra no modelo. Passe o mouse (ou toque) num nome para ver a explicação.</Typography>
              <FormGroup row>
                {cat.variantes.map(v => (
                  <FormControlLabel key={v.id} control={<Checkbox size="small" checked={vars.includes(v.id)} onChange={() => alternar(vars, setVars, v.id)} />}
                                    label={<NomeVariante id={v.id} cat={cat} />} />))}
              </FormGroup>
            </Box>
            <Divider />
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(220px, 100%), 1fr))" }}>
              <TextField select label="Empresas" SelectProps={{ multiple: true, renderValue: v => (v as string[]).length ? `${(v as string[]).length} selecionada(s)` : "Todas" }}
                         value={emps} onChange={e => setEmps(e.target.value as unknown as string[])}>
                {empresas?.map(e => <MenuItem key={e.id} value={String(e.id)}><Checkbox size="small" checked={emps.includes(String(e.id))} />{e.nome}</MenuItem>)}
              </TextField>
              {(["treino", "validacao", "teste"] as const).map(k => (
                <TextField key={k} type="number" label={`${k === "validacao" ? "Validação" : k[0].toUpperCase() + k.slice(1)} (%)`}
                           value={prop[k]} error={!somaOk} inputProps={{ min: 0, max: 100, step: 5 }}
                           onChange={e => setProp({ ...prop, [k]: Number(e.target.value) })}
                           helperText={k === "teste" && !somaOk ? "As três precisam somar 100%" : undefined} />))}
            </Box>
            <Stack>
              <FormControlLabel control={<Switch checked={comExemplo} onChange={e => setComExemplo(e.target.checked)} />}
                                label="Incluir os dados de exemplo (case sintético)" />
              {pode("admin") && <FormControlLabel control={<Switch checked={ativar} onChange={e => setAtivar(e.target.checked)} />}
                                                  label="Usar o melhor modelo na plataforma ao terminar" />}
              <Typography variant="body2" color="text.secondary">
                Cada combinação é ajustada no treino, comparada na validação e o vencedor é medido uma vez no teste.
                Com tudo marcado são {algs.length * vars.length} combinações; pode levar alguns minutos.
              </Typography>
            </Stack>
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={aoFechar}>Cancelar</Button>
        <Button variant="contained" startIcon={<PlayArrow />} disabled={!algs.length || !vars.length || !somaOk} onClick={iniciar}>
          Iniciar treino</Button>
      </DialogActions>
    </Dialog>
  );
}

// ------------------------------------------------------------------ treinos
function ListaTreinos({ treinos }: { treinos: Treino[] }) {
  if (!treinos.length) return <Typography color="text.secondary">Nenhum treino iniciado pela plataforma ainda.</Typography>;
  const cor = { concluido: "success", erro: "error", interrompido: "warning", rodando: "info", "na fila": "default" } as const;
  return (
    <Stack spacing={1.5}>
      {treinos.map(t => (
        <Card key={t.id}><CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "center" }} justifyContent="space-between">
            <Box sx={{ minWidth: 0 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip size="small" color={cor[t.estado]} label={t.estado} />
                <Typography variant="body2" color="text.secondary">{data(t.criado_em, true)} · {t.usuario} ·
                  {" "}{t.params.algoritmos.length || "todos os"} algoritmos × {t.params.variantes.length || "todas as"} representações</Typography>
              </Stack>
              <Typography variant="body2" sx={{ mt: .5 }}>
                {t.estado === "rodando" ? t.etapa : t.mensagem}
                {t.modelo && <> · <MuiLink component={Link} to={`/modelos/${t.modelo}`}>ver modelo {t.modelo}</MuiLink></>}
              </Typography>
            </Box>
            {(t.estado === "rodando" || t.estado === "na fila") && (
              <Box sx={{ width: { xs: "100%", sm: 220 } }}>
                <LinearProgress variant="determinate" value={t.progresso * 100} />
                <Typography variant="caption" color="text.secondary">{pct(t.progresso)}</Typography>
              </Box>)}
          </Stack>
        </CardContent></Card>))}
    </Stack>
  );
}

// ------------------------------------------------------------------ comparação
function Comparacao({ linhas, escolhido }: { linhas: LinhaComparacao[]; escolhido: { variante: string | null; modelo: string | null } }) {
  const cat = useCatalogo();
  const [ordem, setOrdem] = useState<keyof LinhaComparacao>("posicao");
  const ordenadas = [...linhas].sort((a, b) => ordem === "posicao" ? a.posicao - b.posicao
    : ((b[ordem] as number) ?? -1) - ((a[ordem] as number) ?? -1));
  const melhorPorAlg = useMemo(() => {
    const m = new Map<string, LinhaComparacao>();
    linhas.forEach(l => { const a = m.get(l.modelo); if (!a || (l.val_balanced_accuracy ?? 0) > (a.val_balanced_accuracy ?? 0)) m.set(l.modelo, l); });
    return [...m.values()].sort((a, b) => (b.val_balanced_accuracy ?? 0) - (a.val_balanced_accuracy ?? 0));
  }, [linhas]);
  const eh = (l: LinhaComparacao) => separarModelo(escolhido.modelo).alg === l.modelo && escolhido.variante === l.variante;
  const cab = (k: keyof LinhaComparacao, t: string) => (
    <TableCell align="right" sx={{ cursor: "pointer", color: ordem === k ? "primary.main" : undefined }} onClick={() => setOrdem(k)}>{t}</TableCell>);
  return (
    <Stack spacing={2}>
      <Secao titulo="Melhor resultado de cada algoritmo (validação)">
        <Stack spacing={1}>
          {melhorPorAlg.map(l => (
            <Stack key={l.modelo} direction="row" spacing={2} alignItems="center">
              <Box sx={{ width: { xs: 150, sm: 270 }, flexShrink: 0 }}><NomeAlgoritmo id={l.modelo} cat={cat} /></Box>
              <Box sx={{ flex: 1 }}>{barra(l.val_balanced_accuracy, eh(l))}</Box>
              <Box sx={{ width: 230, display: { xs: "none", md: "block" }, color: "text.secondary" }}>
                <NomeVariante id={l.variante} cat={cat} /></Box>
            </Stack>))}
        </Stack>
        <Typography variant="caption" color="text.secondary">Acurácia balanceada na validação, com a melhor representação de cada algoritmo; a barra vai de 0,5 (acaso) a 1. Passe o mouse (ou toque) num nome para ver o que é.</Typography>
      </Secao>
      <Secao titulo={`Todas as combinações (${linhas.length})`}>
        <TableContainer sx={{ maxHeight: 520 }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow>
              <TableCell sx={{ cursor: "pointer" }} onClick={() => setOrdem("posicao")}>#</TableCell>
              <TableCell sx={{ minWidth: 220 }}>Algoritmo</TableCell><TableCell sx={{ minWidth: 180 }}>Representação da curva</TableCell>
              {cab("cv_balanced_accuracy", "CV treino")}{cab("val_balanced_accuracy", "Validação")}{cab("val_roc_auc", "AUC val.")}
              {cab("teste_balanced_accuracy", "Teste")}{cab("teste_sensibilidade", "Sens.")}{cab("teste_especificidade", "Espec.")}
              {cab("teste_roc_auc", "AUC teste")}
            </TableRow></TableHead>
            <TableBody>{ordenadas.map(l => (
              <TableRow key={`${l.variante}-${l.modelo}`} hover selected={eh(l)}>
                <TableCell>{l.posicao}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={.5} alignItems="flex-start">
                    <NomeAlgoritmo id={l.modelo} cat={cat} />
                    {eh(l) && <Tooltip title="Combinação escolhida (melhor na validação)"><StarOutline fontSize="small" color="primary" /></Tooltip>}
                  </Stack>
                </TableCell>
                <TableCell><NomeVariante id={l.variante} cat={cat} /></TableCell>
                <TableCell align="right">{num(l.cv_balanced_accuracy, 3)}{l.cv_ba_desvio !== null && <Typography component="span" variant="caption" color="text.secondary"> ±{num(l.cv_ba_desvio, 2)}</Typography>}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>{num(l.val_balanced_accuracy, 3)}</TableCell>
                <TableCell align="right">{num(l.val_roc_auc, 3)}</TableCell>
                <TableCell align="right">{num(l.teste_balanced_accuracy, 3)}</TableCell>
                <TableCell align="right">{num(l.teste_sensibilidade, 2)}</TableCell>
                <TableCell align="right">{num(l.teste_especificidade, 2)}</TableCell>
                <TableCell align="right">{num(l.teste_roc_auc, 3)}</TableCell>
              </TableRow>))}
            </TableBody>
          </Table>
        </TableContainer>
        <Typography variant="caption" color="text.secondary">
          Valores de acurácia balanceada. A escolha é pela validação (★); o teste mostra como cada combinação se sairia, mas não participa da escolha.
          Clique nos títulos para ordenar. Os nomes têm a explicação de cada algoritmo e representação: passe o mouse (ou toque) neles.
        </Typography>
      </Secao>
    </Stack>
  );
}

// ------------------------------------------------------------------ título do modelo
function NomeModeloTitulo({ modelo }: { modelo: string | null }) {
  const cat = useCatalogo();
  const { alg, variante } = separarModelo(modelo);
  const a = cat?.algoritmos.find(x => x.id === alg);
  return (
    <Box>
      <ComDica dica={dicaAlgoritmo(alg, a)}>
        <Typography variant="h6" component="h2" sx={{ lineHeight: 1.25 }}>
          {a ? a.nome : alg} {a && <Box component="span" sx={{ fontWeight: 400, color: "text.secondary", fontSize: ".9em" }}>· {a.ajuste}</Box>}
        </Typography>
      </ComDica>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: .25 }} flexWrap="wrap" useFlexGap>
        <Typography variant="body2" color="text.secondary">com a representação</Typography>
        <NomeVariante id={variante} cat={cat} />
      </Stack>
    </Box>
  );
}

// ------------------------------------------------------------------ página
export default function Modelos() {
  const { id } = useParams();
  const navegar = useNavigate();
  const { pode } = useAuth();
  const avisar = useAvisos();
  const lista = useCarregar<ModeloResumo[]>("/api/modelos");
  const treinos = useCarregar<Treino[]>("/api/treinos");
  const emUso = lista.dados?.find(m => m.em_uso);
  const alvo = id || emUso?.id || lista.dados?.[0]?.id || null;
  const det = useCarregar<ModeloDetalhe>(alvo ? `/api/modelos/${alvo}` : null);
  const [aba, setAba] = useState("comparacao");
  const [novo, setNovo] = useState(false);
  const [ativar, setAtivar] = useState<string | null>(null);
  const cat = useCatalogo();

  const rodando = treinos.dados?.some(t => t.estado === "rodando" || t.estado === "na fila");
  useEffect(() => {                                 // acompanha o treino em andamento
    if (!rodando) return;
    const t = setInterval(() => { treinos.recarregar(); }, 2000);
    return () => clearInterval(t);
  }, [rodando]);  // eslint-disable-line react-hooks/exhaustive-deps
  const [estavaRodando, setEstavaRodando] = useState(false);
  useEffect(() => {
    if (rodando) setEstavaRodando(true);
    else if (estavaRodando) { setEstavaRodando(false); lista.recarregar(); avisar("Treino terminado."); }
  }, [rodando]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function usar(mid: string) {
    setAtivar(null);
    try { await api.post(`/api/modelos/${mid}/ativar`); avisar(`Modelo ${mid} em uso.`); lista.recarregar(); det.recarregar(); }
    catch (e) { avisar((e as Error).message, "error"); }
  }

  const m = det.dados;
  return (
    <>
      <Cabecalho titulo="Modelos" sub="Acurácia do modelo em uso, comparação dos algoritmos, histórico e novos treinos."
                 acoes={pode("editar") && <Button variant="contained" startIcon={<PlayArrow />} disabled={rodando} onClick={() => setNovo(true)}>
                   {rodando ? "Treino em andamento…" : "Treinar modelos"}</Button>} />
      {lista.erro && <Alert severity="error">{lista.erro}</Alert>}
      {treinos.dados?.filter(t => t.estado === "rodando" || t.estado === "na fila").map(t => (
        <Alert key={t.id} severity="info" sx={{ mb: 2 }}>
          Treinando: {t.etapa} ({pct(t.progresso)})
          <LinearProgress variant="determinate" value={t.progresso * 100} sx={{ mt: 1 }} />
        </Alert>))}
      {lista.dados && !lista.dados.length && (
        <Alert severity="info" sx={{ mb: 2 }}>Nenhum modelo treinado ainda. Use “Treinar modelos” (com os dados do banco) ou <code>fiep experimento</code>.</Alert>)}
      {m && (
        <Stack spacing={2}>
          <Card sx={{ borderColor: m.em_uso ? "primary.main" : undefined }}>
            <CardContent>
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                <Box>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <NomeModeloTitulo modelo={m.modelo} />
                    {m.em_uso ? <Chip size="small" color="primary" icon={<CheckCircleOutline />} label="em uso" />
                      : <Chip size="small" variant="outlined" label="não está em uso" />}
                    {m.protocolo && <Chip size="small" variant="outlined" label={`protocolo ${m.protocolo}`} />}
                  </Stack>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>
                    Registro <Box component="span" sx={mono}>{m.id}</Box> · {data(m.criado_em, true)} · {m.n_amostras} amostras no treino + validação
                    {m.resumo.amostras_teste ? ` · ${m.resumo.amostras_teste} no teste` : ""} · limiar {pct(m.limiar)}
                  </Typography>
                </Box>
                {!m.em_uso && pode("admin") && <Box><Button variant="outlined" onClick={() => setAtivar(m.id)}>Usar este modelo</Button></Box>}
              </Stack>
              <Box sx={{ display: "grid", gap: 1.5, mt: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(150px, 100%), 1fr))" }}>
                <Kpi rotulo="Acurácia (teste)" valor={pct(m.teste_acuracia, 1)} cor="primary.main" sub="acertos / total de eletrodos" />
                <Kpi rotulo="Acurácia balanceada" valor={num(m.teste_balanced_accuracy, 3)} sub="média de sens. e espec." />
                <Kpi rotulo="Sensibilidade" valor={pct(m.teste_sensibilidade, 1)} sub="contaminadas detectadas" />
                <Kpi rotulo="Especificidade" valor={pct(m.teste_especificidade, 1)} sub="limpas reconhecidas" />
                <Kpi rotulo="AUC" valor={num(m.teste_roc_auc, 3)} sub="separação das classes" />
                <Kpi rotulo="Por amostra" valor={num(m.teste_amostra_balanced_accuracy, 3)} sub="acur. balanceada, média dos eletrodos" />
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                Medido no conjunto de teste, que não participou de nenhuma escolha. Validação {num(m.validacao_balanced_accuracy, 3)} ·
                validação cruzada no treino {num(m.cv_balanced_accuracy, 3)}{m.regressor && ` · carga estimada por ${cat?.regressores?.find(r => r.id === m.regressor)?.nome || m.regressor}`}.
              </Typography>
            </CardContent>
          </Card>

          <Tabs value={aba} onChange={(_, v) => setAba(v)} variant="scrollable" sx={{ borderBottom: 1, borderColor: "divider" }}>
            <Tab value="comparacao" label="Comparação de algoritmos" />
            <Tab value="graficos" label="Gráficos" />
            <Tab value="carga" label="Carga (regressão)" />
            <Tab value="historico" label={`Histórico (${lista.dados?.length ?? 0})`} />
            <Tab value="treinos" label="Treinos" />
          </Tabs>

          {aba === "comparacao" && (m.comparacao.length
            ? <Comparacao linhas={m.comparacao} escolhido={{ variante: m.variante, modelo: m.modelo }} />
            : <Alert severity="info">Este modelo não tem a comparação gravada (pasta do experimento não encontrada).</Alert>)}

          {aba === "graficos" && (
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))" }}>
              {m.figuras.map(f => (
                <Secao key={f.arquivo} titulo={f.titulo}>
                  <Box component="img" src={`/api/modelos/${m.id}/figuras/${f.arquivo}`} alt={f.titulo} loading="lazy"
                       sx={{ width: "100%", borderRadius: 1, bgcolor: "#fff" }} />
                </Secao>))}
              {m.resumo.formula_sisso && (
                <Secao titulo="Fórmula do SISSO (modelo interpretável)">
                  <Typography sx={{ ...mono, wordBreak: "break-word" }}>{m.resumo.formula_sisso}</Typography>
                </Secao>)}
              {!m.figuras.length && <Alert severity="info">Sem figuras para este modelo.</Alert>}
            </Box>)}

          {aba === "carga" && (
            <Secao titulo="Estimativa da carga (log₁₀ UFC/mL) nas contaminadas">
              {m.regressao.length ? (
                <TableContainer><Table size="small">
                  <TableHead><TableRow><TableCell>Regressor</TableCell><TableCell>Representação da curva</TableCell>
                    <TableCell align="right">RMSE CV</TableCell><TableCell align="right">RMSE validação</TableCell>
                    <TableCell align="right">RMSE teste</TableCell><TableCell align="right">R² teste</TableCell></TableRow></TableHead>
                  <TableBody>{m.regressao.map((r, i) => (
                    <TableRow key={i} hover selected={r.modelo === m.regressor && r.variante === m.variante}>
                      <TableCell><NomeAlgoritmo id={r.modelo} cat={cat} /></TableCell><TableCell><NomeVariante id={r.variante} cat={cat} /></TableCell>
                      <TableCell align="right">{num(r.cv_rmse, 2)}</TableCell><TableCell align="right">{num(r.val_rmse, 2)}</TableCell>
                      <TableCell align="right">{num(r.teste_rmse, 2)}</TableCell><TableCell align="right">{num(r.teste_r2, 2)}</TableCell>
                    </TableRow>))}</TableBody>
                </Table></TableContainer>
              ) : <Typography color="text.secondary">Sem carga de referência suficiente para a regressão.</Typography>}
              <Typography variant="caption" color="text.secondary">RMSE em log₁₀ UFC/mL (menor é melhor). Linha destacada: regressor usado pelo modelo.</Typography>
            </Secao>)}

          {aba === "historico" && (
            <Card><TableContainer>
              <Table size="small">
                <TableHead><TableRow><TableCell>Modelo</TableCell><TableCell>Treinado em</TableCell>
                  <TableCell align="right">Acurácia</TableCell><TableCell align="right">Acur. balanceada</TableCell>
                  <TableCell align="right">AUC</TableCell><TableCell align="right">Por amostra</TableCell>
                  <TableCell align="right">Amostras</TableCell><TableCell /></TableRow></TableHead>
                <TableBody>{lista.dados?.map(x => (
                  <TableRow key={x.id} hover selected={x.id === m.id}>
                    <TableCell>
                      <MuiLink component={Link} to={`/modelos/${x.id}`} fontWeight={550}>{textoModelo(x.modelo, cat)}</MuiLink>
                      {x.em_uso && <Chip size="small" color="primary" label="em uso" sx={{ ml: 1 }} />}
                      <Typography variant="caption" display="block" color="text.secondary" sx={mono}>{x.id}</Typography>
                    </TableCell>
                    <TableCell>{data(x.criado_em, true)}</TableCell>
                    <TableCell align="right">{pct(x.teste_acuracia, 1)}</TableCell>
                    <TableCell align="right">{num(x.teste_balanced_accuracy, 3)}</TableCell>
                    <TableCell align="right">{num(x.teste_roc_auc, 3)}</TableCell>
                    <TableCell align="right">{num(x.teste_amostra_balanced_accuracy, 3)}</TableCell>
                    <TableCell align="right">{x.n_amostras}</TableCell>
                    <TableCell align="right">{!x.em_uso && pode("admin") && <Button size="small" onClick={() => setAtivar(x.id)}>Usar</Button>}</TableCell>
                  </TableRow>))}
                </TableBody>
              </Table>
            </TableContainer></Card>)}

          {aba === "treinos" && <ListaTreinos treinos={treinos.dados || []} />}
        </Stack>
      )}
      {!m && alvo && !det.erro && <Skeleton variant="rounded" height={320} />}
      {det.erro && <Alert severity="error">{det.erro}</Alert>}
      {!alvo && treinos.dados && treinos.dados.length > 0 && <Box sx={{ mt: 2 }}><ListaTreinos treinos={treinos.dados} /></Box>}

      <NovoTreino aberto={novo} aoFechar={() => setNovo(false)} aoIniciar={() => { treinos.recarregar(); setAba("treinos"); }} />
      <Confirmar aberto={!!ativar} titulo="Usar este modelo?" acao="Usar" aoFechar={() => setAtivar(null)}
                 aoConfirmar={() => { usar(ativar!); if (id && id !== ativar) navegar(`/modelos/${ativar}`); }}
                 texto="A plataforma e o fiep prever passam a usar este modelo nas próximas previsões. Dá para voltar ao anterior a qualquer momento." />
    </>
  );
}
