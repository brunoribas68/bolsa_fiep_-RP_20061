import FileDownloadOutlined from "@mui/icons-material/FileDownloadOutlined";
import { Alert, Box, Button, MenuItem, Skeleton, Stack, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Cabecalho, Kpi, Secao } from "../componentes/comum";
import { csv } from "../componentes/exportar";
import TabelaEnsaios from "../componentes/TabelaEnsaios";
import { num } from "../formato";
import type { Calibracao, Empresa, Ensaio } from "../tipos";
import { useCarregar } from "../usar";

export default function Ensaios() {
  const [busca, setBusca] = useSearchParams();
  const empresa = busca.get("empresa_id") || "";
  const [tipo, setTipo] = useState("");
  const [eletrodo, setEletrodo] = useState("");
  const { dados: empresas } = useCarregar<Empresa[]>("/api/empresas");
  const { dados, erro, recarregar } = useCarregar<{ ensaios: Ensaio[]; calibracao: Calibracao | null }>(
    `/api/ensaios${empresa ? `?empresa_id=${empresa}` : ""}`);
  const itens = useMemo(() => (dados?.ensaios || []).filter(e => (!tipo || e.tipo === tipo) && (!eletrodo || e.eletrodo_id === eletrodo)),
                        [dados, tipo, eletrodo]);
  const todos = dados?.ensaios || [];
  const eletrodos = [...new Set(todos.map(e => e.eletrodo_id))].sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true }));
  const aprovados = todos.filter(e => e.qc_flag !== "FAIL");
  const nB = aprovados.filter(e => e.tipo === "branco").length, nR = aprovados.filter(e => e.tipo === "rna").length;
  const cal = dados?.calibracao;
  return (
    <>
      <Cabecalho titulo="Ensaios" sub="A base do genossensor: um voltamograma por linha. Clique numa linha para ver a curva e editar."
                 acoes={<Button variant="outlined" startIcon={<FileDownloadOutlined />} disabled={!itens.length}
                                onClick={() => csv(itens as unknown as Record<string, unknown>[], COLUNAS_CSV, "ensaios.csv")}>CSV</Button>} />
      {erro && <Alert severity="error">{erro}</Alert>}
      {!dados ? <Skeleton variant="rounded" height={300} /> : (
        <Stack spacing={2}>
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(190px, 100%), 1fr))" }}>
            <Kpi rotulo="Branco (não contaminado)" valor={nB} sub="aprovados no QC" />
            <Kpi rotulo="RNA (contaminado)" valor={nR} cor="error.main" sub="aprovados no QC" />
            <Kpi rotulo="Eletrodos" valor={eletrodos.length} />
            <Kpi rotulo="Calibração" valor={cal ? `R² ${num(cal.r2, 2)}` : "—"}
                 sub={cal ? `${num(cal.inclinacao_pct_por_decada, 1)} % de queda por década · LOD ${cal.lod_ng_ml !== null ? `${num(cal.lod_ng_ml, 3)} ng/mL` : "—"}`
                          : "precisa de 3 RNA ligados a um branco"} />
          </Box>
          {(nB < 3 || nR < 3) && (
            <Alert severity="info">Para treinar o modelo são precisos pelo menos 3 ensaios de branco e 3 de RNA aprovados
              (hoje: {nB} e {nR}). O ideal é ter vários eletrodos, cada um com o branco e o RNA.</Alert>)}
          <Secao titulo={`${itens.length} ensaio(s)`} acoes={
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <TextField select size="small" label="Empresa" value={empresa} sx={{ minWidth: 160 }} fullWidth={false}
                         onChange={e => { const p = new URLSearchParams(busca); e.target.value ? p.set("empresa_id", e.target.value) : p.delete("empresa_id"); setBusca(p); }}>
                <MenuItem value="">todas</MenuItem>
                {empresas?.map(e => <MenuItem key={e.id} value={String(e.id)}>{e.nome}</MenuItem>)}
              </TextField>
              <TextField select size="small" label="Tipo" value={tipo} onChange={e => setTipo(e.target.value)} sx={{ minWidth: 120 }} fullWidth={false}>
                <MenuItem value="">todos</MenuItem><MenuItem value="branco">Branco</MenuItem><MenuItem value="rna">RNA</MenuItem>
              </TextField>
              <TextField select size="small" label="Eletrodo" value={eletrodo} onChange={e => setEletrodo(e.target.value)} sx={{ minWidth: 120 }} fullWidth={false}>
                <MenuItem value="">todos</MenuItem>
                {eletrodos.map(e => <MenuItem key={e} value={e}>{e}</MenuItem>)}
              </TextField>
            </Stack>}>
            <TabelaEnsaios itens={itens} aoMudar={recarregar} />
            {!todos.length && <Typography color="text.secondary" sx={{ mt: 1 }}>
              Envie os .nox em Coletas → Nova coleta, ou pela linha de comando: <code>fiep rna importar --entrada dados/rna</code>.</Typography>}
          </Secao>
        </Stack>
      )}
    </>
  );
}

const COLUNAS_CSV = [
  { id: "arquivo", nome: "arquivo" }, { id: "eletrodo_id", nome: "eletrodo" }, { id: "tipo", nome: "tipo" },
  { id: "concentracao", nome: "concentracao_ng_ml" }, { id: "elemento_captura", nome: "elemento_captura" },
  { id: "bacteria", nome: "bacteria" }, { id: "e_pico_v", nome: "e_pico_v" }, { id: "i_pico_ua", nome: "i_pico_ua" },
  { id: "altura_ua", nome: "altura_ua" }, { id: "queda_pct", nome: "queda_vs_branco_pct" }, { id: "qc_flag", nome: "qc" },
  { id: "canal", nome: "canal" }, { id: "medido_em", nome: "medido_em" }, { id: "observacoes", nome: "observacoes" },
];
