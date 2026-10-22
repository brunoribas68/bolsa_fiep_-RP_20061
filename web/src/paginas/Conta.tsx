import { Alert, Box, Button, Stack, Table, TableBody, TableCell, TableRow, TextField } from "@mui/material";
import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Cabecalho, Secao } from "../componentes/comum";
import { NOME_PAPEL } from "../tipos";

export default function Conta() {
  const { usuario } = useAuth();
  const [f, setF] = useState({ atual: "", nova: "", repetir: "" });
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  async function trocar() {
    setMsg(null);
    if (f.nova !== f.repetir) return setMsg({ ok: false, t: "As senhas novas não conferem." });
    try {
      await api.post("/api/auth/senha", { atual: f.atual, nova: f.nova });
      setF({ atual: "", nova: "", repetir: "" });
      setMsg({ ok: true, t: "Senha alterada. As sessões abertas em outros computadores foram encerradas." });
    } catch (e) { setMsg({ ok: false, t: (e as Error).message }); }
  }
  return (
    <>
      <Cabecalho titulo="Minha conta" />
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(340px, 100%), 1fr))" }}>
        <Secao titulo="Perfil">
          <Table size="small"><TableBody>
            {[["Nome", usuario?.nome], ["E-mail", usuario?.email], ["Perfil", usuario && NOME_PAPEL[usuario.papel]],
              ["Instituição", usuario?.instituicao || "—"]].map(([k, v]) => (
              <TableRow key={k}><TableCell sx={{ color: "text.secondary", pl: 0 }}>{k}</TableCell><TableCell>{v}</TableCell></TableRow>))}
          </TableBody></Table>
        </Secao>
        <Secao titulo="Trocar senha">
          <Stack spacing={2}>
            <TextField label="Senha atual" type="password" autoComplete="current-password" value={f.atual} onChange={e => setF({ ...f, atual: e.target.value })} />
            <TextField label="Nova senha" type="password" autoComplete="new-password" value={f.nova} helperText="Mínimo de 10 caracteres"
                       onChange={e => setF({ ...f, nova: e.target.value })} />
            <TextField label="Repita a nova senha" type="password" autoComplete="new-password" value={f.repetir}
                       error={!!f.repetir && f.repetir !== f.nova} onChange={e => setF({ ...f, repetir: e.target.value })} />
            {msg && <Alert severity={msg.ok ? "success" : "error"}>{msg.t}</Alert>}
            <Box><Button variant="contained" disabled={!f.atual || f.nova.length < 10} onClick={trocar}>Trocar senha</Button></Box>
          </Stack>
        </Secao>
      </Box>
    </>
  );
}
