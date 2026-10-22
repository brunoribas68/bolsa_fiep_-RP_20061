import { Link as MuiLink, MenuItem, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { num } from "../formato";
import { NOME_CONJUNTO, type AmostraLinha } from "../tipos";
import { useAvisos } from "./avisos";
import { ChipResultado, ChipRotulo, mono } from "./comum";

function Edicao({ a, aoMudar }: { a: AmostraLinha; aoMudar: (n: AmostraLinha) => void }) {
  const avisar = useAvisos();
  const [salvando, setSalvando] = useState(false);
  async function salvar(campos: Partial<AmostraLinha>) {
    setSalvando(true);
    try {
      await api.patch(`/api/amostras/${encodeURIComponent(a.sample_id)}`, campos);
      aoMudar({ ...a, ...campos });
      avisar(`${a.sample_id} atualizada.`);
    } catch (e) { avisar((e as Error).message, "error"); } finally { setSalvando(false); }
  }
  return (
    <>
      <TableCell sx={{ minWidth: 170 }}>
        <TextField select fullWidth={false} sx={{ minWidth: 160 }} disabled={salvando}
                   inputProps={{ "aria-label": `Resultado de ${a.sample_id}` }}
                   value={a.contamination_status === null ? "" : String(a.contamination_status)}
                   onChange={e => salvar({ contamination_status: e.target.value === "" ? null : Number(e.target.value) })}>
          <MenuItem value=""><em>Sem resultado</em></MenuItem>
          <MenuItem value="1">Contaminada</MenuItem>
          <MenuItem value="0">Não contaminada</MenuItem>
        </TextField>
      </TableCell>
      <TableCell align="right">
        <TextField fullWidth={false} sx={{ width: 90 }} disabled={salvando} defaultValue={a.sample_log10_mean_cfu_ml ?? ""}
                   inputProps={{ inputMode: "decimal", style: { textAlign: "right" }, "aria-label": `Carga de ${a.sample_id}` }}
                   onBlur={e => {
                     const v = e.target.value.trim().replace(",", ".");
                     const novo = v === "" ? null : Number(v);
                     if (novo !== a.sample_log10_mean_cfu_ml && (novo === null || !Number.isNaN(novo)))
                       salvar({ sample_log10_mean_cfu_ml: novo });
                   }} />
      </TableCell>
    </>
  );
}

export default function TabelaAmostras({ itens, aoMudar, mostrarEmpresa = true }: {
  itens: AmostraLinha[]; aoMudar: (a: AmostraLinha) => void; mostrarEmpresa?: boolean;
}) {
  const { pode } = useAuth();
  const editar = pode("editar");
  return (
    <TableContainer>
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>Amostra</TableCell>{mostrarEmpresa && <TableCell>Empresa</TableCell>}
          <TableCell>Plaqueamento</TableCell><TableCell align="right">Carga (log₁₀ UFC/mL)</TableCell>
          <TableCell align="right">Eletrodos completos</TableCell><TableCell>Uso</TableCell><TableCell>Última previsão</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {itens.map(a => (
            <TableRow key={a.sample_id} hover>
              <TableCell><MuiLink component={Link} to={`/amostras/${encodeURIComponent(a.sample_id)}`} sx={mono}>{a.sample_id}</MuiLink></TableCell>
              {mostrarEmpresa && <TableCell>{a.empresa || <Typography color="text.secondary">—</Typography>}</TableCell>}
              {editar ? <Edicao a={a} aoMudar={aoMudar} /> : (
                <><TableCell><ChipRotulo v={a.contamination_status} /></TableCell>
                  <TableCell align="right">{num(a.sample_log10_mean_cfu_ml, 1)}</TableCell></>
              )}
              <TableCell align="right">
                <Typography variant="body2" color={a.n_completas ? "text.primary" : "warning.main"} fontWeight={a.n_completas ? 400 : 600}>
                  {a.n_completas} de {a.n_replicas}
                </Typography>
              </TableCell>
              <TableCell>{NOME_CONJUNTO[a.conjunto || ""].replace(" (50/25/25)", "")}</TableCell>
              <TableCell><ChipResultado r={a.ultima_previsao} /></TableCell>
            </TableRow>
          ))}
          {!itens.length && <TableRow><TableCell colSpan={7} align="center" sx={{ py: 4, color: "text.secondary" }}>Nenhuma amostra.</TableCell></TableRow>}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
