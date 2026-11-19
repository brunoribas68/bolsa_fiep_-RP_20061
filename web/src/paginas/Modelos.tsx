import CheckCircleOutline from "@mui/icons-material/CheckCircleOutline";
import PlayArrow from "@mui/icons-material/PlayArrow";
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
import { NomeAlgoritmo, NomeVariante, useCatalogo } from "../componentes/nomes";
import { concTexto, data, num, pct } from "../formato";
import type { Catalogo, Empresa, LinhaPlacar, Modelo, Treino } from "../tipos";
import { useCarregar } from "../usar";

function barra(v: number | null | undefined, destaque = false) {
  if (v === null || v === undefined) return <Typography variant="body2" color="text.secondary">—</Typography>;
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 120, color: "text.disabled" }}>
      <LinearProgress variant="determinate" value={Math.max(0, (v - 0.5) / 0.5) * 100} sx={{ flex: 1, height: 6, borderRadius: 3 }}
                      color={destaque ? "primary" : "inherit"} />
      <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", minWidth: 40, textAlign: "right", fontWeight: destaque ? 700 : 400 }}>
        {num(v, 3)}</Typography>
    </Stack>
  );
}

// ------------------------------------------------------------------ novo treino
function NovoTreino({ aberto, aoFechar, aoIniciar }: { aberto: boolean; aoFechar: () => void; aoIniciar: () => void }) {
  const { pode } = useAuth();
  const avisar = useAvisos();
  const cat = useCatalogo();
  const { dados: empresas } = useCarregar<Empresa[]>(aberto ? "/api/empresas" : null);
  const [algs, setAlgs] = useState<string[]>([]);
  const [vars, setVars] = useState<string[]>([]);
  const [emps, setEmps] = useState<string[]>([]);
  const [ativar, setAtivar] = useState(false);
  useEffect(() => { if (cat) { setAlgs(cat.algoritmos.map(a => a.id)); setVars(cat.variantes.map(v => v.id)); } }, [cat]);

  const familias = useMemo(() => {
    const m = new Map<string, Catalogo["algoritmos"]>();
    (cat?.algoritmos || []).forEach(a => m.set(a.familia, [...(m.get(a.familia) || []), a]));
    return [...m.entries()];
  }, [cat]);
  const alternar = (lista: string[], set: (l: string[]) => void, id: string) =>
    set(lista.includes(id) ? lista.filter(x => x !== id) : [...lista, id]);
  const pares = algs.filter(a => a !== "sisso").length * vars.length + (algs.includes("sisso") && vars.includes("pico") ? 1 : 0);

  async function iniciar() {
    try {
      await api.post<Treino>("/api/treinos", { algoritmos: algs, variantes: vars, empresas: emps.map(Number), ativar });
      avisar("Treino iniciado."); aoIniciar(); aoFechar();
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
              <Typography variant="caption" color="text.secondary">O que do voltamograma o modelo vê. Passe o mouse (ou toque) num nome para ver a explicação.</Typography>
              <FormGroup row>
                {cat.variantes.map(v => (
                  <FormControlLabel key={v.id} control={<Checkbox size="small" checked={vars.includes(v.id)} onChange={() => alternar(vars, setVars, v.id)} />}
                                    label={<NomeVariante id={v.id} cat={cat} />} />))}
              </FormGroup>
            </Box>
            <Divider />
            <TextField select label="Empresas" SelectProps={{ multiple: true, renderValue: v => (v as string[]).length ? `${(v as string[]).length} selecionada(s)` : "Todas" }}
                       value={emps} onChange={e => setEmps(e.target.value as unknown as string[])} sx={{ maxWidth: 360 }}>
              {empresas?.map(e => <MenuItem key={e.id} value={String(e.id)}><Checkbox size="small" checked={emps.includes(String(e.id))} />{e.nome}</MenuItem>)}
            </TextField>
            <Stack>
              {pode("admin") && <FormControlLabel control={<Switch checked={ativar} onChange={e => setAtivar(e.target.checked)} />}
                                                  label="Usar o melhor modelo na plataforma ao terminar" />}
              <Typography variant="body2" color="text.secondary">
                Cada combinação é avaliada por validação cruzada que nunca separa um eletrodo entre treino e avaliação. Com 8 ou mais
                eletrodos, cerca de 25 % deles ficam guardados como teste e o vencedor é medido neles uma única vez.
                São {pares} combinações (o SISSO só roda com as medidas do pico); pode levar alguns minutos.
              </Typography>
            </Stack>
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={aoFechar}>Cancelar</Button>
        <Button variant="contained" startIcon={<PlayArrow />} disabled={!pares} onClick={iniciar}>Iniciar treino</Button>
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
type ColPlacar = "posicao" | "balanced_accuracy" | "roc_auc" | "sensibilidade" | "especificidade";

function Comparacao({ m }: { m: Modelo }) {
  const cat = useCatalogo();
  const [ordem, setOrdem] = useState<ColPlacar>("posicao");
  const ok = m.placar.filter(l => !l.erro);
  const ordenadas = [...m.placar].sort((a, b) => ordem === "posicao" ? a.posicao - b.posicao : (b[ordem] ?? -1) - (a[ordem] ?? -1));
  const melhorPorAlg = useMemo(() => {
    const mp = new Map<string, LinhaPlacar>();
    ok.forEach(l => { const a = mp.get(l.algoritmo); if (!a || (l.balanced_accuracy ?? 0) > (a.balanced_accuracy ?? 0)) mp.set(l.algoritmo, l); });
    return [...mp.values()].sort((a, b) => (b.balanced_accuracy ?? 0) - (a.balanced_accuracy ?? 0) || a.posicao - b.posicao);
  }, [ok]);
  const eh = (l: LinhaPlacar) => l.algoritmo === m.algoritmo && l.representacao === m.representacao;
  const cab = (k: ColPlacar, t: string) => (
    <TableCell align="right" sx={{ cursor: "pointer", color: ordem === k ? "primary.main" : undefined }} onClick={() => setOrdem(k)}>{t}</TableCell>);
  return (
    <Stack spacing={2}>
      <Secao titulo="Melhor resultado de cada algoritmo">
        <Stack spacing={1}>
          {melhorPorAlg.map(l => (
            <Stack key={l.algoritmo} direction="row" spacing={2} alignItems="center">
              <Box sx={{ width: { xs: 150, sm: 270 }, flexShrink: 0 }}><NomeAlgoritmo id={l.algoritmo} cat={cat} /></Box>
              <Box sx={{ flex: 1 }}>{barra(l.balanced_accuracy, eh(l))}</Box>
              <Box sx={{ width: 170, display: { xs: "none", md: "block" }, color: "text.secondary" }}>
                <NomeVariante id={l.representacao} cat={cat} /></Box>
            </Stack>))}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Acurácia balanceada na validação cruzada por eletrodo, com a melhor representação de cada algoritmo; a barra vai de 0,5 (acaso) a 1.
          Com poucos eletrodos vários empatam em 1,0: o desempate é pelo mais simples.</Typography>
      </Secao>
      <Secao titulo={`Todas as combinações (${m.placar.length})`}>
        <TableContainer sx={{ maxHeight: 520 }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow>
              <TableCell sx={{ cursor: "pointer" }} onClick={() => setOrdem("posicao")}>#</TableCell>
              <TableCell>Algoritmo</TableCell><TableCell>Representação</TableCell>
              {cab("balanced_accuracy", "Acur. balanceada")}{cab("roc_auc", "AUC")}{cab("sensibilidade", "Sensib.")}{cab("especificidade", "Especif.")}
            </TableRow></TableHead>
            <TableBody>{ordenadas.map(l => (
              <TableRow key={`${l.representacao}-${l.algoritmo}`} hover selected={eh(l)}>
                <TableCell>{l.posicao}</TableCell>
                <TableCell><NomeAlgoritmo id={l.algoritmo} cat={cat} /></TableCell>
                <TableCell><NomeVariante id={l.representacao} cat={cat} /></TableCell>
                {l.erro ? <TableCell colSpan={4}><Tooltip title={l.erro}><Typography variant="body2" color="error">não treinou</Typography></Tooltip></TableCell> : <>
                  <TableCell align="right">{barra(l.balanced_accuracy, eh(l))}</TableCell>
                  <TableCell align="right">{num(l.roc_auc, 3)}</TableCell>
                  <TableCell align="right">{pct(l.sensibilidade)}</TableCell>
                  <TableCell align="right">{pct(l.especificidade)}</TableCell></>}
              </TableRow>))}
            </TableBody>
          </Table>
        </TableContainer>
        <Typography variant="caption" color="text.secondary">Linha destacada: a combinação escolhida. Clique no cabeçalho para ordenar.</Typography>
      </Secao>
    </Stack>
  );
}

function Matriz({ mc }: { mc: number[][] }) {
  const cel = (v: number, certo: boolean) => (
    <TableCell align="center" sx={{ fontWeight: 700, fontSize: 18, color: certo ? "success.main" : v ? "error.main" : "text.disabled" }}>{v}</TableCell>);
  return (
    <Table size="small" sx={{ maxWidth: 380 }}>
      <TableHead><TableRow><TableCell /><TableCell align="center">previsto branco</TableCell><TableCell align="center">previsto RNA</TableCell></TableRow></TableHead>
      <TableBody>
        <TableRow><TableCell>é branco</TableCell>{cel(mc[0][0], true)}{cel(mc[0][1], false)}</TableRow>
        <TableRow><TableCell>é RNA</TableCell>{cel(mc[1][0], false)}{cel(mc[1][1], true)}</TableRow>
      </TableBody>
    </Table>
  );
}

// ------------------------------------------------------------------ página
export default function Modelos() {
  const { id } = useParams();
  const navegar = useNavigate();
  const { pode } = useAuth();
  const avisar = useAvisos();
  const lista = useCarregar<Modelo[]>("/api/modelos");
  const treinos = useCarregar<Treino[]>("/api/treinos");
  const emUso = lista.dados?.find(m => m.em_uso);
  const alvo = id || emUso?.id || lista.dados?.[0]?.id || null;
  const det = useCarregar<Modelo>(alvo ? `/api/modelos/${alvo}` : null);
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
  const ref = m?.metricas_teste || m?.metricas_cv;
  return (
    <>
      <Cabecalho titulo="Modelos" sub="O modelo em uso, a comparação dos algoritmos, o histórico e novos treinos."
                 acoes={pode("editar") && <Button variant="contained" startIcon={<PlayArrow />} disabled={rodando} onClick={() => setNovo(true)}>
                   {rodando ? "Treino em andamento…" : "Treinar modelos"}</Button>} />
      {lista.erro && <Alert severity="error">{lista.erro}</Alert>}
      {treinos.dados?.filter(t => t.estado === "rodando" || t.estado === "na fila").map(t => (
        <Alert key={t.id} severity="info" sx={{ mb: 2 }}>
          Treinando: {t.etapa} ({pct(t.progresso)})
          <LinearProgress variant="determinate" value={t.progresso * 100} sx={{ mt: 1 }} />
        </Alert>))}
      {treinos.dados?.[0]?.estado === "erro" && !rodando && (
        <Alert severity="warning" sx={{ mb: 2 }}>Último treino não terminou: {treinos.dados[0].mensagem}</Alert>)}
      {lista.dados && !lista.dados.length && (
        <Alert severity="info" sx={{ mb: 2 }}>Nenhum modelo treinado ainda. Com pelo menos 3 ensaios de branco e 3 de RNA na base, use
          “Treinar modelos” ou <code>fiep rna treinar</code>.</Alert>)}
      {m && ref && (
        <Stack spacing={2}>
          <Card sx={{ borderColor: m.em_uso ? "primary.main" : undefined }}>
            <CardContent>
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={2}>
                <Box>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <NomeAlgoritmo id={m.algoritmo} cat={cat} linha />
                    {m.em_uso ? <Chip size="small" color="primary" icon={<CheckCircleOutline />} label="em uso" />
                      : <Chip size="small" variant="outlined" label="não está em uso" />}
                    {!m.confiavel && <Chip size="small" color="warning" label="ainda não confiável" />}
                  </Stack>
                  <Stack direction="row" spacing={.75} alignItems="center" sx={{ mt: .25 }}>
                    <Typography variant="body2" color="text.secondary">com a representação</Typography>
                    <NomeVariante id={m.representacao} cat={cat} />
                  </Stack>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>
                    Registro <Box component="span" sx={mono}>{m.id}</Box> · {data(m.criado_em, true)} · {m.dados.n_ensaios} curvas
                    ({m.dados.n_branco} branco, {m.dados.n_rna} RNA) de {m.dados.n_eletrodos} eletrodo(s) · concentrações:{" "}
                    {m.dados.concentracoes_ng_ml.map(concTexto).join(", ")}
                  </Typography>
                </Box>
                {!m.em_uso && pode("admin") && <Box><Button variant="outlined" onClick={() => setAtivar(m.id)}>Usar este modelo</Button></Box>}
              </Stack>
              <Box sx={{ display: "grid", gap: 1.5, mt: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(150px, 100%), 1fr))" }}>
                <Kpi rotulo={`Acurácia balanceada (${m.referencia})`} valor={num(ref.balanced_accuracy, 3)} cor="primary.main" sub="média de sensibilidade e especificidade" />
                <Kpi rotulo="Sensibilidade" valor={pct(ref.sensibilidade, 1)} sub="RNA reconhecido" />
                <Kpi rotulo="Especificidade" valor={pct(ref.especificidade, 1)} sub="branco reconhecido" />
                <Kpi rotulo="AUC" valor={num(ref.roc_auc, 3)} sub="separação das classes" />
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                {m.metricas_teste
                  ? `Medido no teste: ${m.dados.n_teste} curvas dos eletrodos ${m.dados.eletrodos_teste.join(", ")}, que não participaram de nenhuma escolha. No treino, ${m.validacao}: acurácia balanceada ${num(m.metricas_cv.balanced_accuracy, 3)}.`
                  : `Sem teste independente: o número é o da ${m.validacao}, que tende a ser otimista.`}
              </Typography>
              {m.avisos.map(a => <Alert key={a} severity="warning" sx={{ mt: 1.5 }}>{a}</Alert>)}
            </CardContent>
          </Card>

          <Tabs value={aba} onChange={(_, v) => setAba(v)} variant="scrollable" sx={{ borderBottom: 1, borderColor: "divider" }}>
            <Tab value="comparacao" label="Comparação de algoritmos" />
            {m.metricas_teste?.matriz_confusao && <Tab value="teste" label="Teste" />}
            <Tab value="historico" label={`Histórico (${lista.dados?.length ?? 0})`} />
            <Tab value="treinos" label="Treinos" />
          </Tabs>

          {aba === "comparacao" && <Comparacao m={m} />}
          {aba === "teste" && m.metricas_teste?.matriz_confusao && (
            <Secao titulo="Matriz de confusão no teste"><Matriz mc={m.metricas_teste.matriz_confusao} /></Secao>)}
          {aba === "historico" && (
            <Card><TableContainer>
              <Table size="small">
                <TableHead><TableRow><TableCell>Modelo</TableCell><TableCell>Treinado em</TableCell>
                  <TableCell align="right">Acur. balanceada</TableCell><TableCell>Medida em</TableCell>
                  <TableCell align="right">Curvas</TableCell><TableCell align="right">Eletrodos</TableCell><TableCell /></TableRow></TableHead>
                <TableBody>{lista.dados?.map(x => (
                  <TableRow key={x.id} hover selected={x.id === m.id}>
                    <TableCell>
                      <MuiLink component={Link} to={`/modelos/${x.id}`} fontWeight={550}>{x.algoritmo_nome} · {x.representacao_nome}</MuiLink>
                      {x.em_uso && <Chip size="small" color="primary" label="em uso" sx={{ ml: 1 }} />}
                      <Typography variant="caption" display="block" color="text.secondary" sx={mono}>{x.id}</Typography>
                    </TableCell>
                    <TableCell>{data(x.criado_em, true)}</TableCell>
                    <TableCell align="right">{num(x.ab_referencia, 3)}</TableCell>
                    <TableCell>{x.referencia}</TableCell>
                    <TableCell align="right">{x.dados.n_ensaios}</TableCell>
                    <TableCell align="right">{x.dados.n_eletrodos}</TableCell>
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
                 texto="A plataforma e o fiep rna prever passam a usar este modelo nas próximas previsões. Dá para voltar ao anterior a qualquer momento." />
    </>
  );
}

