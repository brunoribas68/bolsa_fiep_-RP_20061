import WarningAmberOutlined from "@mui/icons-material/WarningAmberOutlined";
import {
  Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Skeleton, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, TableSortLabel, TextField, Tooltip, Typography, useTheme,
} from "@mui/material";
import { useMemo, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { corEnsaio, data, num } from "../formato";
import type { Ensaio, EnsaioDetalhe } from "../tipos";
import { useCarregar } from "../usar";
import { useAvisos } from "./avisos";
import { ChipTipo, mono, SeloQC } from "./comum";
import Confirmar from "./Confirmar";
import GraficoCurvas from "./GraficoCurvas";

type Coluna = "arquivo" | "eletrodo_id" | "tipo" | "e_pico_v" | "altura_ua" | "queda_pct";

/** Tabela da base (uma linha por voltamograma); clique abre a curva e a edição. */
export default function TabelaEnsaios({ itens, aoMudar }: { itens: Ensaio[]; aoMudar: () => void }) {
  const [ordem, setOrdem] = useState<{ col: Coluna; asc: boolean }>({ col: "eletrodo_id", asc: true });
  const [aberto, setAberto] = useState<number | null>(null);
  const ordenados = useMemo(() => [...itens].sort((a, b) => {
    const chave = (e: Ensaio) => ordem.col === "tipo" ? (e.tipo === "branco" ? -1 : e.concentracao) : e[ordem.col];
    const [x, y] = [chave(a), chave(b)];
    const r = x === null ? 1 : y === null ? -1
      : typeof x === "string" ? x.localeCompare(String(y), "pt-BR", { numeric: true }) : (x as number) - (y as number);
    return (ordem.asc ? r : -r) || (a.tipo === "branco" ? -1 : 1) || a.concentracao - b.concentracao;
  }), [itens, ordem]);
  const cab = (col: Coluna, nome: string, dir = false) => (
    <TableCell align={dir ? "right" : "left"} sortDirection={ordem.col === col ? (ordem.asc ? "asc" : "desc") : false}>
      <TableSortLabel active={ordem.col === col} direction={ordem.asc ? "asc" : "desc"}
                      onClick={() => setOrdem(o => ({ col, asc: o.col === col ? !o.asc : true }))}>{nome}</TableSortLabel>
    </TableCell>
  );
  return (
    <>
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead><TableRow>
            {cab("arquivo", "Arquivo")}{cab("eletrodo_id", "Eletrodo")}{cab("tipo", "Tipo")}
            <TableCell>Elemento</TableCell>
            {cab("e_pico_v", "E pico (V)", true)}{cab("altura_ua", "Altura (µA)", true)}
            <TableCell align="right" sortDirection={ordem.col === "queda_pct" ? (ordem.asc ? "asc" : "desc") : false}>
              <Tooltip title="Quanto o pico caiu em relação ao branco do mesmo eletrodo. O sensor é signal-off: com o RNA, o pico tem de cair.">
                <TableSortLabel active={ordem.col === "queda_pct"} direction={ordem.asc ? "asc" : "desc"}
                                onClick={() => setOrdem(o => ({ col: "queda_pct", asc: o.col === "queda_pct" ? !o.asc : false }))}>
                  Queda</TableSortLabel>
              </Tooltip>
            </TableCell>
            <TableCell>QC</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {ordenados.map(e => (
              <TableRow key={e.id} hover onClick={() => setAberto(e.id)} sx={{ cursor: "pointer" }}>
                <TableCell sx={{ ...mono, whiteSpace: "nowrap" }}>{e.arquivo}</TableCell>
                <TableCell>{e.eletrodo_id}</TableCell>
                <TableCell><ChipTipo tipo={e.tipo} conc={e.concentracao} /></TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{e.elemento_captura || "—"}</TableCell>
                <TableCell align="right" sx={mono}>{num(e.e_pico_v, 3)}</TableCell>
                <TableCell align="right" sx={mono}>{num(e.altura_ua, 2)}</TableCell>
                <TableCell align="right" sx={mono}>
                  {e.tipo === "rna" && e.queda_pct !== null ? (
                    <Stack direction="row" spacing={.5} justifyContent="flex-end" alignItems="center">
                      {e.abaixo_do_branco === false && (
                        <Tooltip title="Pico acima do branco do eletrodo: o contrário do esperado para o sensor.">
                          <WarningAmberOutlined fontSize="small" color="warning" /></Tooltip>)}
                      <span>{num(e.queda_pct, 1)}%</span>
                    </Stack>) : e.tipo === "rna" ? <Tooltip title="Sem branco do mesmo eletrodo"><span>—</span></Tooltip> : ""}
                </TableCell>
                <TableCell><SeloQC v={e.qc_flag} /></TableCell>
              </TableRow>
            ))}
            {!itens.length && <TableRow><TableCell colSpan={8} align="center" sx={{ py: 4, color: "text.secondary" }}>
              Nenhum ensaio ainda.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Box>
      {aberto !== null && <EnsaioDialogo id={aberto} aoFechar={() => setAberto(null)} aoMudar={aoMudar} />}
    </>
  );
}

function EnsaioDialogo({ id, aoFechar, aoMudar }: { id: number; aoFechar: () => void; aoMudar: () => void }) {
  const { dados: e, setDados } = useCarregar<EnsaioDetalhe>(`/api/ensaios/${id}`);
  const { pode } = useAuth();
  const avisar = useAvisos();
  const escuro = useTheme().palette.mode === "dark";
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [apagar, setApagar] = useState(false);
  const editando = form !== null;

  function editar() {
    if (!e) return;
    setForm({ tipo: e.tipo, concentracao: e.tipo === "rna" ? String(e.concentracao) : "", eletrodo_id: e.eletrodo_id,
              elemento_captura: e.elemento_captura || "", bacteria: e.bacteria || "", qc_flag: e.qc_flag || "",
              observacoes: e.observacoes || "" });
  }
  async function salvar() {
    if (!form) return;
    try {
      const corpo = { ...form, concentracao: form.tipo === "rna" ? Number(form.concentracao.replace(",", ".")) : 0 };
      setDados(await api.patch<EnsaioDetalhe>(`/api/ensaios/${id}`, corpo));
      setForm(null); aoMudar(); avisar("Ensaio atualizado.");
    } catch (x) { avisar((x as Error).message, "error"); }
  }
  async function remover() {
    setApagar(false);
    try { await api.del(`/api/ensaios/${id}`); aoMudar(); aoFechar(); avisar("Ensaio apagado."); }
    catch (x) { avisar((x as Error).message, "error"); }
  }

  const series = e ? [
    ...(e.branco ? [{ nome: `Branco do eletrodo (${e.branco.arquivo})`, cor: corEnsaio("branco", 0, [], escuro),
                      x: e.branco.potential_v, y: e.branco.current_ua }] : []),
    { nome: e.arquivo || `Ensaio ${e.id}`, cor: corEnsaio(e.tipo, e.concentracao, [e.concentracao], escuro),
      x: e.potential_v, y: e.current_ua },
  ] : [];
  const campo = (k: string, rotulo: string, extra: object = {}) => (
    <TextField label={rotulo} value={form?.[k] ?? ""} size="small" fullWidth {...extra}
               onChange={ev => setForm(f => f && { ...f, [k]: ev.target.value })} />
  );
  return (
    <Dialog open onClose={aoFechar} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pb: 1 }}>
        <Box component="span" sx={mono}>{e?.arquivo || "…"}</Box>
        {e && <Typography variant="body2" color="text.secondary">
          Eletrodo {e.eletrodo_id}{e.canal ? ` · canal ${e.canal}` : ""} · medido {data(e.medido_em, true)}
          {e.procedimento ? ` · "${e.procedimento}"` : ""}</Typography>}
      </DialogTitle>
      <DialogContent>
        {!e ? <Skeleton variant="rounded" height={300} /> : (
          <Stack spacing={2}>
            <GraficoCurvas series={series} rotY="δI (µA)" />
            <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
              {([["Tipo", <ChipTipo key="t" tipo={e.tipo} conc={e.concentracao} />], ["E pico", `${num(e.e_pico_v, 3)} V`],
                 ["I pico", `${num(e.i_pico_ua, 2)} µA`], ["Base", `${num(e.i_base_ua, 2)} µA`],
                 ["Altura", `${num(e.altura_ua, 2)} µA`], ["Largura", `${num(e.largura_v, 3)} V`],
                 ["Queda vs branco", e.tipo === "rna" && e.queda_pct !== null ? `${num(e.queda_pct, 1)}%` : "—"],
                 ["Elemento de captura", e.elemento_captura || "—"], ["Bactéria", e.bacteria || "—"]] as const).map(([r, v]) => (
                <Box key={r}><Typography variant="caption" color="text.secondary">{r}</Typography>
                  <Typography variant="body2" component="div">{v}</Typography></Box>))}
            </Stack>
            {!e.branco && e.tipo === "rna" && <Typography variant="body2" color="warning.main">
              Sem branco do eletrodo {e.eletrodo_id} com o mesmo elemento de captura: não dá para calcular a queda do pico.</Typography>}
            {e.observacoes && !editando && <Typography variant="body2" color="text.secondary">Observações: {e.observacoes}</Typography>}
            {editando && (
              <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(auto-fit, minmax(min(180px, 100%), 1fr))" }}>
                {campo("tipo", "Tipo", { select: true, children: [<MenuItem key="b" value="branco">Branco (não contaminado)</MenuItem>,
                                                                   <MenuItem key="r" value="rna">RNA (contaminado)</MenuItem>] })}
                {form!.tipo === "rna" && campo("concentracao", "Concentração (ng/mL)", { inputProps: { inputMode: "decimal" } })}
                {campo("eletrodo_id", "Eletrodo")}
                {campo("elemento_captura", "Elemento de captura")}
                {campo("bacteria", "Bactéria")}
                {campo("qc_flag", "Controle de qualidade", { select: true, children: [
                  <MenuItem key="" value="">— (aprovado)</MenuItem>, <MenuItem key="p" value="PASS">Aprovado</MenuItem>,
                  <MenuItem key="f" value="FAIL">Reprovado (fica fora do treino)</MenuItem>] })}
                <Box sx={{ gridColumn: "1 / -1" }}>{campo("observacoes", "Observações", { multiline: true, minRows: 2 })}</Box>
              </Box>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        {pode("editar") && !editando && <Button color="error" onClick={() => setApagar(true)} sx={{ mr: "auto" }}>Apagar</Button>}
        {editando ? <>
          <Button onClick={() => setForm(null)}>Cancelar</Button>
          <Button variant="contained" onClick={salvar}>Salvar</Button>
        </> : <>
          {pode("editar") && <Button onClick={editar} disabled={!e}>Editar</Button>}
          <Button variant="contained" onClick={aoFechar}>Fechar</Button>
        </>}
      </DialogActions>
      <Confirmar aberto={apagar} perigo titulo="Apagar este ensaio?" acao="Apagar" aoFechar={() => setApagar(false)}
                 aoConfirmar={remover} texto={`${e?.arquivo} sai da base. Para voltar, envie o arquivo de novo.`} />
    </Dialog>
  );
}

