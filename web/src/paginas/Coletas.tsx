import AddIcon from "@mui/icons-material/Add";
import { Alert, Box, Button, Card, Link as MuiLink, Table, TableBody, TableCell, TableHead, TableRow, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { Cabecalho } from "../componentes/comum";
import { data } from "../formato";
import type { Coleta } from "../tipos";
import { useCarregar } from "../usar";

export default function Coletas() {
  const { pode } = useAuth();
  const { dados, erro } = useCarregar<Coleta[]>("/api/coletas");
  return (
    <>
      <Cabecalho titulo="Coletas" sub="Cada envio de .nox, com quem enviou e quando."
                 acoes={pode("editar") && <Button variant="contained" startIcon={<AddIcon />} component={Link} to="/coletas/nova">Nova coleta</Button>} />
      {erro && <Alert severity="error">{erro}</Alert>}
      <Card><Box sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Coleta</TableCell><TableCell>Empresa</TableCell><TableCell>Data</TableCell>
            <TableCell align="right">Branco</TableCell><TableCell align="right">RNA</TableCell>
            <TableCell align="right">Avisos</TableCell><TableCell>Enviada por</TableCell></TableRow></TableHead>
          <TableBody>
            {dados?.map(c => (
              <TableRow key={c.id} hover>
                <TableCell><MuiLink component={Link} to={`/coletas/${c.id}`} fontWeight={550}>{c.descricao || `Coleta #${c.id}`}</MuiLink></TableCell>
                <TableCell>{c.empresa || "—"}</TableCell>
                <TableCell>{data(c.data_coleta || c.criado_em)}</TableCell>
                <TableCell align="right">{c.n_branco}</TableCell><TableCell align="right">{c.n_rna}</TableCell>
                <TableCell align="right" sx={{ color: c.avisos.length ? "warning.main" : "text.secondary" }}>{c.avisos.length}</TableCell>
                <TableCell>{c.criado_por || <Typography variant="body2" color="text.secondary">linha de comando</Typography>}</TableCell>
              </TableRow>
            ))}
            {dados && !dados.length && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 4, color: "text.secondary" }}>Nenhuma coleta ainda.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Box></Card>
    </>
  );
}
