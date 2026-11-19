import AddIcon from "@mui/icons-material/Add";
import { Alert, Box, Button, Chip, LinearProgress, Link as MuiLink, Skeleton, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { Cabecalho, ChipTipo, Kpi, Secao } from "../componentes/comum";
import { NomeAlgoritmo, NomeVariante, useCatalogo } from "../componentes/nomes";
import { data, num } from "../formato";
import { useCarregar } from "../usar";

interface PainelDados {
  branco: number; rna: number; eletrodos: number; reprovados: number; empresas: number; coletas: number; min_por_classe: number;
  por_concentracao: { tipo: "branco" | "rna"; concentracao: number; ensaios: number; eletrodos: number }[];
  coletas_recentes: { id: number; descricao: string | null; criado_em: string; n_ensaios: number; empresa: string | null; criado_por: string | null }[];
  modelo: { id: string; algoritmo: string; representacao: string; ab_referencia: number; referencia: string; confiavel: boolean;
            criado_em: string; n_ensaios: number } | null;
}

const grade = (min: number) => ({ display: "grid", gap: 2, gridTemplateColumns: `repeat(auto-fit, minmax(min(${min}px, 100%), 1fr))` });

export default function Painel() {
  const { usuario, pode } = useAuth();
  const cat = useCatalogo();
  const { dados: d, erro } = useCarregar<PainelDados>("/api/painel");
  const maior = Math.max(1, ...(d?.por_concentracao || []).map(p => p.ensaios));
  const falta = d ? Math.max(0, d.min_por_classe - d.branco) + Math.max(0, d.min_por_classe - d.rna) : 0;
  return (
    <>
      <Cabecalho titulo={`Olá, ${usuario?.nome.split(" ")[0]}`} sub="A base do genossensor (branco e RNA) e o modelo em uso."
                 acoes={pode("editar") && <Button variant="contained" startIcon={<AddIcon />} component={Link} to="/coletas/nova">Nova coleta</Button>} />
      {erro && <Alert severity="error">{erro}</Alert>}
      {!d && !erro && <Box sx={grade(200)}>{[0, 1, 2, 3].map(i => <Skeleton key={i} variant="rounded" height={110} />)}</Box>}
      {d && (
        <Stack spacing={2}>
          <Box sx={grade(200)}>
            <Kpi rotulo="Branco" valor={d.branco} sub="não contaminado" />
            <Kpi rotulo="RNA" valor={d.rna} cor="error.main" sub="contaminado" />
            <Kpi rotulo="Eletrodos" valor={d.eletrodos} sub={`${d.empresas} empresa(s) · ${d.coletas} coleta(s)`} />
            <Kpi rotulo="Reprovados no QC" valor={d.reprovados} cor={d.reprovados ? "warning.main" : undefined}
                 sub={<MuiLink component={Link} to="/ensaios">ver a base</MuiLink>} />
          </Box>
          <Box sx={grade(360)}>
            <Secao titulo="Modelo em uso" acoes={<Button size="small" component={Link} to="/modelos">detalhes e comparação</Button>}>
              {d.modelo ? (
                <Stack spacing={1.25}>
                  <NomeAlgoritmo id={d.modelo.algoritmo} cat={cat} linha />
                  <Stack direction="row" spacing={.75} alignItems="center">
                    <Typography variant="body2" color="text.secondary">com a representação</Typography>
                    <NomeVariante id={d.modelo.representacao} cat={cat} />
                  </Stack>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip label={`Acurácia balanceada ${num(d.modelo.ab_referencia, 3)}`} color={d.modelo.confiavel ? "primary" : "warning"} />
                    <Chip label={d.modelo.referencia === "teste" ? "medida no teste" : "medida na validação cruzada"} variant="outlined" />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    {d.modelo.n_ensaios} curvas no treino · {data(d.modelo.criado_em, true)}
                    {!d.modelo.confiavel && " · abaixo de 0,7: as previsões saem INCONCLUSIVO"}
                  </Typography>
                </Stack>
              ) : falta > 0 ? (
                <Stack spacing={1}>
                  <Alert severity="info">Para treinar, faltam {Math.max(0, d.min_por_classe - d.branco)} branco(s) e{" "}
                    {Math.max(0, d.min_por_classe - d.rna)} RNA (mínimo de {d.min_por_classe} de cada).</Alert>
                  <LinearProgress variant="determinate" value={100 * (Math.min(d.branco, d.min_por_classe) + Math.min(d.rna, d.min_por_classe)) / (2 * d.min_por_classe)} />
                </Stack>
              ) : <Alert severity="info">Há dados para treinar: use “Treinar modelos” em <MuiLink component={Link} to="/modelos">Modelos</MuiLink>.</Alert>}
            </Secao>
            <Secao titulo="Coletas recentes" acoes={<Button size="small" component={Link} to="/coletas">ver todas</Button>}>
              {d.coletas_recentes.length ? (
                <Table size="small"><TableBody>
                  {d.coletas_recentes.map(c => (
                    <TableRow key={c.id} hover>
                      <TableCell sx={{ pl: 0 }}>
                        <MuiLink component={Link} to={`/coletas/${c.id}`} fontWeight={550}>{c.descricao || `Coleta #${c.id}`}</MuiLink>
                        <Typography variant="body2" color="text.secondary">{c.empresa || "sem empresa"} · {c.criado_por || "linha de comando"}</Typography>
                      </TableCell>
                      <TableCell align="right">{c.n_ensaios} ensaios</TableCell>
                      <TableCell align="right" sx={{ color: "text.secondary", pr: 0 }}>{data(c.criado_em)}</TableCell>
                    </TableRow>))}
                </TableBody></Table>
              ) : <Typography color="text.secondary">Nenhuma coleta ainda.</Typography>}
            </Secao>
          </Box>
          <Secao titulo="Ensaios por concentração">
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead><TableRow><TableCell>Tipo</TableCell><TableCell align="right">Ensaios</TableCell>
                  <TableCell align="right">Eletrodos</TableCell><TableCell sx={{ width: "45%" }} /></TableRow></TableHead>
                <TableBody>{d.por_concentracao.map(p => (
                  <TableRow key={`${p.tipo}${p.concentracao}`} hover>
                    <TableCell><ChipTipo tipo={p.tipo} conc={p.concentracao} /></TableCell>
                    <TableCell align="right">{p.ensaios}</TableCell><TableCell align="right">{p.eletrodos}</TableCell>
                    <TableCell><Box sx={{ height: 8, width: `${100 * p.ensaios / maior}%`, borderRadius: 1,
                                          bgcolor: p.tipo === "branco" ? "text.secondary" : "error.main", opacity: .7 }} /></TableCell>
                  </TableRow>))}
                {!d.por_concentracao.length && <TableRow><TableCell colSpan={4} align="center" sx={{ color: "text.secondary", py: 3 }}>Sem ensaios.</TableCell></TableRow>}
                </TableBody>
              </Table>
            </Box>
            <Typography variant="caption" color="text.secondary">Repetições em eletrodos diferentes valem mais que muitas medidas do mesmo eletrodo.</Typography>
          </Secao>
        </Stack>
      )}
    </>
  );
}
