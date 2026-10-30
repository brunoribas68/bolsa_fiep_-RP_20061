import AddIcon from "@mui/icons-material/Add";
import { Alert, Box, Button, Chip, Link as MuiLink, Skeleton, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { Cabecalho, Kpi, Secao } from "../componentes/comum";
import { data, num, pct } from "../formato";
import { useCarregar } from "../usar";
import { ComDica, dicaAlgoritmo, NomeVariante, separarModelo, useCatalogo } from "../componentes/nomes";

interface PainelDados {
  amostras: number; contaminadas: number; nao_contaminadas: number; sem_rotulo: number; medicoes: number;
  replicas_completas: number; replicas: number; reprovadas_qc: number; empresas: number; coletas: number;
  por_empresa: { empresa: string; contaminadas: number; nao_contaminadas: number; sem_rotulo: number }[];
  coletas_recentes: { id: number; descricao: string | null; criado_em: string; n_amostras: number; empresa: string | null; criado_por: string | null }[];
  modelo: { id: string; algoritmo: string; limiar: number; acuracia_teste: number | null; ab_teste: number | null; auc_teste: number | null; n_amostras: number } | null;
}

const grade = (min: number) => ({ display: "grid", gap: 2, gridTemplateColumns: `repeat(auto-fit, minmax(min(${min}px, 100%), 1fr))` });

function NomeModelo({ modelo }: { modelo: string }) {
  const cat = useCatalogo();
  const { alg, variante } = separarModelo(modelo);
  const a = cat?.algoritmos.find(x => x.id === alg);
  return (
    <Box>
      <ComDica dica={dicaAlgoritmo(alg, a)}>
        <Typography fontWeight={600}>{a ? a.nome : alg}
          {a && <Typography component="span" color="text.secondary" fontWeight={400}> · {a.ajuste}</Typography>}</Typography>
      </ComDica>
      {variante && <Stack direction="row" spacing={.75} alignItems="center">
        <Typography variant="body2" color="text.secondary">com a representação</Typography><NomeVariante id={variante} cat={cat} /></Stack>}
    </Box>
  );
}

export default function Painel() {
  const { usuario, pode } = useAuth();
  const { dados: d, erro } = useCarregar<PainelDados>("/api/painel");
  return (
    <>
      <Cabecalho titulo={`Olá, ${usuario?.nome.split(" ")[0]}`} sub="Situação do banco de voltamogramas e do modelo em uso."
                 acoes={pode("editar") && <Button variant="contained" startIcon={<AddIcon />} component={Link} to="/coletas/nova">Nova coleta</Button>} />
      {erro && <Alert severity="error">{erro}</Alert>}
      {!d && !erro && <Box sx={grade(200)}>{[0, 1, 2, 3].map(i => <Skeleton key={i} variant="rounded" height={110} />)}</Box>}
      {d && (
        <Stack spacing={2}>
          <Box sx={grade(200)}>
            <Kpi rotulo="Amostras" valor={d.amostras} sub={`${d.empresas} empresas · ${d.coletas} coletas`} />
            <Kpi rotulo="Contaminadas" valor={d.contaminadas} cor="error.main" sub={`${d.nao_contaminadas} não contaminadas`} />
            <Kpi rotulo="Sem resultado de plaqueamento" valor={d.sem_rotulo} cor={d.sem_rotulo ? "warning.main" : undefined}
                 sub={d.sem_rotulo ? <MuiLink component={Link} to="/amostras?rotulo=sem">completar rótulos</MuiLink> : "tudo rotulado"} />
            <Kpi rotulo="Eletrodos completos" valor={d.replicas_completas}
                 sub={`de ${d.replicas} · ${d.reprovadas_qc} medições reprovadas no QC`} />
          </Box>
          <Box sx={grade(360)}>
            <Secao titulo="Modelo em uso" acoes={<Button size="small" component={Link} to="/modelos">detalhes e comparação</Button>}>
              {d.modelo ? (
                <Stack spacing={1.5}>
                  <NomeModelo modelo={d.modelo.algoritmo} />
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip label={`Acurácia ${pct(d.modelo.acuracia_teste, 1)}`} color="primary" />
                    <Chip label={`Acurácia balanceada ${num(d.modelo.ab_teste, 3)}`} color="primary" variant="outlined" />
                    <Chip label={`AUC ${num(d.modelo.auc_teste, 3)}`} variant="outlined" />
                    <Chip label={`limiar ${pct(d.modelo.limiar)}`} variant="outlined" />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    Medido no conjunto de teste · {d.modelo.n_amostras} amostras no treino · registro <code>{d.modelo.id}</code>
                  </Typography>
                </Stack>
              ) : <Alert severity="info">Nenhum modelo treinado ainda. Rode <code>fiep experimento --db dados/fiep.db</code>.</Alert>}
            </Secao>
            <Secao titulo="Coletas recentes" acoes={<Button size="small" component={Link} to="/coletas">ver todas</Button>}>
              {d.coletas_recentes.length ? (
                <Table size="small"><TableBody>
                  {d.coletas_recentes.map(c => (
                    <TableRow key={c.id} hover>
                      <TableCell sx={{ pl: 0 }}>
                        <MuiLink component={Link} to={`/coletas/${c.id}`} fontWeight={550}>{c.descricao || `Coleta #${c.id}`}</MuiLink>
                        <Typography variant="body2" color="text.secondary">{c.empresa || "sem empresa"} · {c.criado_por || "importação"}</Typography>
                      </TableCell>
                      <TableCell align="right">{c.n_amostras} amostras</TableCell>
                      <TableCell align="right" sx={{ color: "text.secondary", pr: 0 }}>{data(c.criado_em)}</TableCell>
                    </TableRow>))}
                </TableBody></Table>
              ) : <Typography color="text.secondary">Nenhuma coleta ainda.</Typography>}
            </Secao>
          </Box>
          <Secao titulo="Amostras por empresa">
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead><TableRow><TableCell>Empresa</TableCell><TableCell align="right">Contaminadas</TableCell>
                  <TableCell align="right">Não contaminadas</TableCell><TableCell align="right">Sem resultado</TableCell>
                  <TableCell sx={{ width: "34%" }}>Distribuição</TableCell></TableRow></TableHead>
                <TableBody>{d.por_empresa.map(e => {
                  const t = e.contaminadas + e.nao_contaminadas + e.sem_rotulo || 1;
                  return (
                    <TableRow key={e.empresa} hover>
                      <TableCell>{e.empresa}</TableCell><TableCell align="right">{e.contaminadas}</TableCell>
                      <TableCell align="right">{e.nao_contaminadas}</TableCell><TableCell align="right">{e.sem_rotulo}</TableCell>
                      <TableCell>
                        <Tooltip title={`${e.contaminadas} contaminadas · ${e.nao_contaminadas} não contaminadas · ${e.sem_rotulo} sem resultado`}>
                          <Stack direction="row" spacing={.25} sx={{ height: 8 }}>
                            <Box sx={{ flex: e.contaminadas / t, bgcolor: "error.main", borderRadius: 1 }} />
                            <Box sx={{ flex: e.nao_contaminadas / t, bgcolor: "success.main", borderRadius: 1 }} />
                            <Box sx={{ flex: e.sem_rotulo / t, bgcolor: "divider", borderRadius: 1 }} />
                          </Stack>
                        </Tooltip>
                      </TableCell>
                    </TableRow>);
                })}
                {!d.por_empresa.length && <TableRow><TableCell colSpan={5} align="center" sx={{ color: "text.secondary", py: 3 }}>Sem amostras.</TableCell></TableRow>}
                </TableBody>
              </Table>
            </Box>
          </Secao>
        </Stack>
      )}
    </>
  );
}
