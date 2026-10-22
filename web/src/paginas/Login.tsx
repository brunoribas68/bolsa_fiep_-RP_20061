import { Alert, Box, Button, Card, CardContent, Stack, TextField, Typography } from "@mui/material";
import { useState, type FormEvent } from "react";
import { Marca } from "../App";
import { useAuth } from "../auth";

export default function Login() {
  const { entrar } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setErro(""); setEnviando(true);
    try { await entrar(email, senha); }
    catch (er) { setErro((er as Error).message); setSenha(""); }
    finally { setEnviando(false); }
  }

  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center", p: 2,
               background: t => t.palette.mode === "light"
                 ? "radial-gradient(1200px 600px at 10% -10%, #dce8f8 0%, transparent 60%), #f4f6f9"
                 : "radial-gradient(1200px 600px at 10% -10%, #1c2a3d 0%, transparent 60%), #0f141a" }}>
      <Card sx={{ width: "min(420px, 100%)", boxShadow: "0 10px 40px rgba(16,24,40,.08)" }}>
        <CardContent sx={{ p: 4 }}>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ color: "primary.main", mb: 3 }}>
            <Marca tamanho={40} />
            <Box sx={{ color: "text.primary" }}>
              <Typography variant="h6">Plataforma FIEP</Typography>
              <Typography variant="body2" color="text.secondary">Monitoramento microbiológico por voltametria</Typography>
            </Box>
          </Stack>
          <Stack component="form" spacing={2} onSubmit={enviar}>
            <TextField label="E-mail" type="email" autoComplete="username" required autoFocus value={email}
                       onChange={e => setEmail(e.target.value)} size="medium" />
            <TextField label="Senha" type="password" autoComplete="current-password" required value={senha}
                       onChange={e => setSenha(e.target.value)} size="medium" />
            {erro && <Alert severity="error" role="alert">{erro}</Alert>}
            <Button type="submit" variant="contained" size="large" disabled={enviando}>
              {enviando ? "Entrando…" : "Entrar"}
            </Button>
            <Typography variant="body2" color="text.secondary">
              Não tem acesso? Peça ao administrador do projeto para criar sua conta.
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
