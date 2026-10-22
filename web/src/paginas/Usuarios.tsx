import KeyOutlined from "@mui/icons-material/KeyOutlined";
import PersonAddOutlined from "@mui/icons-material/PersonAddOutlined";
import {
  Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, MenuItem,
  Stack, Switch, Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip,
} from "@mui/material";
import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAvisos } from "../componentes/avisos";
import { Cabecalho } from "../componentes/comum";
import { data } from "../formato";
import { NOME_PAPEL, type Papel, type Usuario } from "../tipos";
import { useCarregar } from "../usar";

const VAZIO = { nome: "", email: "", senha: "", papel: "colaborador" as Papel, instituicao: "" };

export default function Usuarios() {
  const { usuario: eu } = useAuth();
  const avisar = useAvisos();
  const { dados, erro, recarregar } = useCarregar<Usuario[]>("/api/usuarios");
  const [f, setF] = useState(VAZIO);
  const [criando, setCriando] = useState(false);
  const [senhaDe, setSenhaDe] = useState<Usuario | null>(null);
  const [nova, setNova] = useState("");

  async function acao(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); avisar(ok); recarregar(); return true; }
    catch (e) { avisar((e as Error).message, "error"); return false; }
  }
  return (
    <>
      <Cabecalho titulo="Usuários" sub="Só administradores criam contas. Colaboradores enviam e editam dados; leitores só consultam."
                 acoes={<Button variant="contained" startIcon={<PersonAddOutlined />} onClick={() => { setF(VAZIO); setCriando(true); }}>Nova conta</Button>} />
      {erro && <Alert severity="error">{erro}</Alert>}
      <Card><Box sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead><TableRow><TableCell>Nome</TableCell><TableCell>E-mail</TableCell><TableCell>Perfil</TableCell>
            <TableCell>Instituição</TableCell><TableCell>Último acesso</TableCell><TableCell>Ativo</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>{dados?.map(u => (
            <TableRow key={u.id} hover>
              <TableCell sx={{ fontWeight: 550 }}>{u.nome}{u.id === eu?.id && <Chip size="small" label="você" sx={{ ml: 1 }} />}</TableCell>
              <TableCell>{u.email}</TableCell>
              <TableCell>
                <TextField select fullWidth={false} sx={{ minWidth: 150 }} value={u.papel} inputProps={{ "aria-label": `Perfil de ${u.nome}` }}
                           onChange={e => acao(() => api.patch(`/api/usuarios/${u.id}`, { papel: e.target.value }), "Perfil alterado.")}>
                  {Object.entries(NOME_PAPEL).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
                </TextField>
              </TableCell>
              <TableCell>{u.instituicao || "—"}</TableCell>
              <TableCell sx={{ color: "text.secondary" }}>{data(u.ultimo_login, true)}</TableCell>
              <TableCell>
                <Tooltip title={u.ativo ? "Desativar (encerra as sessões na hora)" : "Reativar"}>
                  <Switch checked={u.ativo} color="success" inputProps={{ "aria-label": `Ativo: ${u.nome}` }}
                          onChange={() => acao(() => api.patch(`/api/usuarios/${u.id}`, { ativo: !u.ativo }), u.ativo ? "Conta desativada." : "Conta reativada.")} />
                </Tooltip>
              </TableCell>
              <TableCell align="right"><Button size="small" startIcon={<KeyOutlined />} onClick={() => { setNova(""); setSenhaDe(u); }}>Redefinir senha</Button></TableCell>
            </TableRow>))}
          </TableBody>
        </Table>
      </Box></Card>

      <Dialog open={criando} onClose={() => setCriando(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nova conta</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField label="Nome" value={f.nome} onChange={e => setF({ ...f, nome: e.target.value })} autoFocus />
            <TextField label="E-mail" type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoComplete="off" />
            <TextField label="Senha inicial" type="password" value={f.senha} onChange={e => setF({ ...f, senha: e.target.value })}
                       autoComplete="new-password" helperText="Mínimo de 10 caracteres. Peça para a pessoa trocar no primeiro acesso." />
            <TextField select label="Perfil" value={f.papel} onChange={e => setF({ ...f, papel: e.target.value as Papel })}>
              {Object.entries(NOME_PAPEL).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
            </TextField>
            <TextField label="Instituição" value={f.instituicao} onChange={e => setF({ ...f, instituicao: e.target.value })} />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCriando(false)}>Cancelar</Button>
          <Button variant="contained" disabled={!f.nome || !f.email || f.senha.length < 10}
                  onClick={async () => { if (await acao(() => api.post("/api/usuarios", f), `Conta de ${f.email} criada.`)) setCriando(false); }}>
            Criar conta</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!senhaDe} onClose={() => setSenhaDe(null)} fullWidth maxWidth="xs">
        <DialogTitle>Redefinir senha</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>Nova senha para <b>{senhaDe?.email}</b>. As sessões abertas dessa conta serão encerradas.</DialogContentText>
          <TextField label="Nova senha" type="password" value={nova} onChange={e => setNova(e.target.value)} autoFocus
                     autoComplete="new-password" helperText="Mínimo de 10 caracteres" />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setSenhaDe(null)}>Cancelar</Button>
          <Button variant="contained" disabled={nova.length < 10}
                  onClick={async () => { if (await acao(() => api.post(`/api/usuarios/${senhaDe!.id}/senha`, { nova }), "Senha redefinida.")) setSenhaDe(null); }}>
            Redefinir</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
