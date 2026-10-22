import AddIcon from "@mui/icons-material/Add";
import EditOutlined from "@mui/icons-material/EditOutlined";
import {
  Alert, Box, Button, Card, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Link as MuiLink, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip,
} from "@mui/material";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAvisos } from "../componentes/avisos";
import { Cabecalho } from "../componentes/comum";
import type { Empresa } from "../tipos";
import { useCarregar } from "../usar";

const VAZIA = { nome: "", cidade: "", segmento: "", observacoes: "" };

export default function Empresas() {
  const { pode } = useAuth();
  const avisar = useAvisos();
  const { dados, erro, recarregar } = useCarregar<Empresa[]>("/api/empresas");
  const [f, setF] = useState(VAZIA);
  const [editando, setEditando] = useState<number | null>(null);
  const [aberto, setAberto] = useState(false);

  const abrir = (e?: Empresa) => {
    setEditando(e?.id ?? null);
    setF(e ? { nome: e.nome, cidade: e.cidade || "", segmento: e.segmento || "", observacoes: e.observacoes || "" } : VAZIA);
    setAberto(true);
  };
  async function salvar() {
    try {
      if (editando) await api.patch(`/api/empresas/${editando}`, f); else await api.post("/api/empresas", f);
      avisar(editando ? "Empresa atualizada." : "Empresa cadastrada.");
      setAberto(false); recarregar();
    } catch (e) { avisar((e as Error).message, "error"); }
  }
  return (
    <>
      <Cabecalho titulo="Empresas" sub="Empresas validadoras onde as coletas são feitas."
                 acoes={pode("editar") && <Button variant="contained" startIcon={<AddIcon />} onClick={() => abrir()}>Cadastrar empresa</Button>} />
      {erro && <Alert severity="error">{erro}</Alert>}
      <Card><Box sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Empresa</TableCell><TableCell>Cidade</TableCell><TableCell>Segmento</TableCell>
            <TableCell align="right">Coletas</TableCell><TableCell align="right">Amostras</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>{dados?.map(e => (
            <TableRow key={e.id} hover><TableCell sx={{ fontWeight: 550 }}>{e.nome}</TableCell><TableCell>{e.cidade || "—"}</TableCell>
              <TableCell>{e.segmento || "—"}</TableCell><TableCell align="right">{e.n_coletas}</TableCell>
              <TableCell align="right"><MuiLink component={Link} to={`/amostras?empresa_id=${e.id}`}>{e.n_amostras}</MuiLink></TableCell>
              <TableCell align="right">{pode("editar") && <Tooltip title="Editar"><IconButton size="small" onClick={() => abrir(e)}><EditOutlined fontSize="small" /></IconButton></Tooltip>}</TableCell></TableRow>))}
            {dados && !dados.length && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 4, color: "text.secondary" }}>Nenhuma empresa cadastrada.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Box></Card>
      <Dialog open={aberto} onClose={() => setAberto(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? "Editar empresa" : "Cadastrar empresa"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField label="Nome" value={f.nome} onChange={e => setF({ ...f, nome: e.target.value })} autoFocus inputProps={{ maxLength: 160 }} />
            <TextField label="Cidade" value={f.cidade} onChange={e => setF({ ...f, cidade: e.target.value })} />
            <TextField label="Segmento" value={f.segmento} onChange={e => setF({ ...f, segmento: e.target.value })} placeholder="ex.: laticínios" />
            <TextField label="Observações" value={f.observacoes} multiline minRows={2} onChange={e => setF({ ...f, observacoes: e.target.value })} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setAberto(false)}>Cancelar</Button>
          <Button variant="contained" disabled={!f.nome.trim()} onClick={salvar}>{editando ? "Salvar" : "Cadastrar"}</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
