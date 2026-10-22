import AddIcon from "@mui/icons-material/Add";
import { Alert, Box, Button, Card, Chip, Link as MuiLink, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { Cabecalho } from "../componentes/comum";
import { data } from "../formato";
import { NOME_CONJUNTO, type Coleta } from "../tipos";
import { useCarregar } from "../usar";

export default function Coletas() {
  const { pode } = useAuth();
  const { dados, erro } = useCarregar<Coleta[]>("/api/coletas");
  return (
    <>
      <Cabecalho titulo="Coletas" sub="Cada envio de voltamogramas das empresas, com quem enviou e quando."
                 acoes={pode("editar") && <Button variant="contained" startIcon={<AddIcon />} component={Link} to="/coletas/nova">Nova coleta</Button>} />
      {erro && <Alert severity="error">{erro}</Alert>}
      <Card><Box sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Coleta</TableCell><TableCell>Empresa</TableCell><TableCell>Data</TableCell>
            <TableCell>Uso</TableCell><TableCell align="right">Amostras</TableCell><TableCell align="right">Medições</TableCell>
            <TableCell align="right">Sem resultado</TableCell><TableCell>Enviada por</TableCell></TableRow></TableHead>
          <TableBody>
            {dados?.map(c => (
              <TableRow key={c.id} hover>
                <TableCell><MuiLink component={Link} to={`/coletas/${c.id}`} fontWeight={550}>{c.descricao || `Coleta #${c.id}`}</MuiLink></TableCell>
                <TableCell>{c.empresa || "—"}</TableCell>
                <TableCell>{data(c.data_coleta || c.criado_em)}</TableCell>
                <TableCell>{NOME_CONJUNTO[c.conjunto || ""].replace(" (50/25/25)", "")}</TableCell>
                <TableCell align="right">{c.n_amostras}</TableCell><TableCell align="right">{c.n_medicoes}</TableCell>
                <TableCell align="right">{c.amostras_sem_rotulo ? <Chip size="small" color="warning" variant="outlined" label={c.amostras_sem_rotulo} /> : 0}</TableCell>
                <TableCell>{c.criado_por || <Typography variant="body2" color="text.secondary">importação</Typography>}</TableCell>
              </TableRow>
            ))}
            {dados && !dados.length && <TableRow><TableCell colSpan={8} align="center" sx={{ py: 4, color: "text.secondary" }}>Nenhuma coleta ainda.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Box></Card>
    </>
  );
}
