import SearchIcon from "@mui/icons-material/Search";
import { Alert, Box, Card, InputAdornment, LinearProgress, MenuItem, Pagination, Stack, TextField, Typography } from "@mui/material";
import { useSearchParams } from "react-router-dom";
import { Cabecalho } from "../componentes/comum";
import TabelaAmostras from "../componentes/TabelaAmostras";
import type { AmostraLinha, Empresa } from "../tipos";
import { useCarregar } from "../usar";

export default function Amostras() {
  const [p, setP] = useSearchParams();
  const pagina = Number(p.get("pagina") || 1);
  const qs = new URLSearchParams({ ...Object.fromEntries(p), por_pagina: "50" }).toString();
  const { dados, erro, setDados, carregando } = useCarregar<{ total: number; itens: AmostraLinha[]; por_pagina: number }>(`/api/amostras?${qs}`);
  const { dados: empresas } = useCarregar<Empresa[]>("/api/empresas");
  const filtro = (k: string, v: string) => {
    const n = new URLSearchParams(p);
    if (v) n.set(k, v); else n.delete(k);
    n.delete("pagina");
    setP(n);
  };
  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  return (
    <>
      <Cabecalho titulo="Amostras" sub="Banco de voltamogramas. Complete aqui o resultado do plaqueamento de cada amostra." />
      <Card>
        <Box sx={{ p: 2, display: "grid", gap: 1.5, gridTemplateColumns: "repeat(auto-fit, minmax(min(190px, 100%), 1fr))" }}>
          <TextField label="Buscar código" defaultValue={p.get("q") || ""} placeholder="ex.: EC_01"
                     InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
                     onKeyDown={e => e.key === "Enter" && filtro("q", (e.target as HTMLInputElement).value)}
                     onBlur={e => e.target.value !== (p.get("q") || "") && filtro("q", e.target.value)} />
          <TextField select label="Empresa" value={p.get("empresa_id") || ""} onChange={e => filtro("empresa_id", e.target.value)}>
            <MenuItem value="">Todas</MenuItem>{empresas?.map(e => <MenuItem key={e.id} value={String(e.id)}>{e.nome}</MenuItem>)}
          </TextField>
          <TextField select label="Plaqueamento" value={p.get("rotulo") || ""} onChange={e => filtro("rotulo", e.target.value)}>
            <MenuItem value="">Todos</MenuItem><MenuItem value="1">Contaminadas</MenuItem>
            <MenuItem value="0">Não contaminadas</MenuItem><MenuItem value="sem">Sem resultado</MenuItem>
          </TextField>
          <TextField select label="Uso" value={p.get("conjunto") || ""} onChange={e => filtro("conjunto", e.target.value)}>
            <MenuItem value="">Todos</MenuItem><MenuItem value="sorteio">Sorteio</MenuItem><MenuItem value="treino">Treino</MenuItem>
            <MenuItem value="validacao">Validação</MenuItem><MenuItem value="teste">Teste</MenuItem>
          </TextField>
        </Box>
        {carregando && <LinearProgress />}
        {erro && <Alert severity="error" sx={{ m: 2 }}>{erro}</Alert>}
        {dados && <TabelaAmostras itens={dados.itens}
          aoMudar={n => setDados(d => d && { ...d, itens: d.itens.map(x => (x.sample_id === n.sample_id ? n : x)) })} />}
        {dados && (
          <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems="center" spacing={1} sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">{dados.total} amostras</Typography>
            <Pagination count={paginas} page={pagina} color="primary" shape="rounded"
                        onChange={(_, v) => { const n = new URLSearchParams(p); n.set("pagina", String(v)); setP(n); }} />
          </Stack>
        )}
      </Card>
    </>
  );
}
