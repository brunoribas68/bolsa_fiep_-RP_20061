import DeleteOutline from "@mui/icons-material/DeleteOutline";
import { Alert, AlertTitle, Box, Button, Skeleton, Stack } from "@mui/material";
import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAvisos } from "../componentes/avisos";
import { Cabecalho, Kpi, Secao } from "../componentes/comum";
import Confirmar from "../componentes/Confirmar";
import TabelaEnsaios from "../componentes/TabelaEnsaios";
import { data } from "../formato";
import type { Coleta } from "../tipos";
import { useCarregar } from "../usar";

export default function ColetaDetalhe() {
  const { id } = useParams();
  const local = useLocation();
  const navegar = useNavigate();
  const avisar = useAvisos();
  const { pode } = useAuth();
  const [confirmar, setConfirmar] = useState(false);
  const { dados: c, erro, recarregar } = useCarregar<Coleta>(`/api/coletas/${id}`);
  const estado = local.state as { criada?: boolean; importacao?: Coleta["importacao"] } | null;

  async function apagar() {
    setConfirmar(false);
    try { await api.del(`/api/coletas/${c!.id}`); avisar("Coleta apagada."); navegar("/coletas"); }
    catch (e) { avisar((e as Error).message, "error"); }
  }

  if (erro) return <Alert severity="error">{erro}</Alert>;
  if (!c) return <Skeleton variant="rounded" height={300} />;
  const contra = (c.ensaios || []).filter(e => e.abaixo_do_branco === false);
  const semBranco = (c.ensaios || []).filter(e => e.tipo === "rna" && e.branco_id === null);
  return (
    <>
      <Cabecalho titulo={c.descricao || `Coleta #${c.id}`}
                 sub={`${c.empresa || "Sem empresa"} · ${data(c.data_coleta || c.criado_em)} · enviada por ${c.criado_por || "linha de comando"} em ${data(c.criado_em, true)}`}
                 acoes={pode("admin") && <Button color="error" variant="outlined" startIcon={<DeleteOutline />} onClick={() => setConfirmar(true)}>Apagar coleta</Button>} />
      <Stack spacing={2}>
        {estado?.criada && estado.importacao && (
          <Alert severity="success">
            {estado.importacao.gravados} ensaio(s) gravado(s) de {estado.importacao.lidos} arquivo(s)
            {estado.importacao.ja_no_banco ? ` · ${estado.importacao.ja_no_banco} já estava(m) na base` : ""}
            {estado.importacao.nao_gravados ? ` · ${estado.importacao.nao_gravados} não gravado(s) (veja os avisos)` : ""}
            {` · ${estado.importacao.ligados_ao_branco} RNA ligado(s) ao branco do eletrodo.`}
          </Alert>)}
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(180px, 100%), 1fr))" }}>
          <Kpi rotulo="Ensaios" valor={c.n_ensaios} />
          <Kpi rotulo="Branco" valor={c.n_branco} sub="não contaminado" />
          <Kpi rotulo="RNA" valor={c.n_rna} sub="contaminado" cor="error.main" />
        </Box>
        {(c.avisos.length > 0 || contra.length > 0 || semBranco.length > 0) && (
          <Alert severity="warning"><AlertTitle>Atenção</AlertTitle>
            <Box component="ul" sx={{ m: 0, pl: 2 }}>
              {contra.map(e => <li key={`c${e.id}`}>{e.arquivo}: pico acima do branco do eletrodo {e.eletrodo_id} (o contrário do esperado)</li>)}
              {semBranco.length > 0 && <li>{semBranco.length} RNA sem branco do mesmo eletrodo: {semBranco.slice(0, 6).map(e => e.arquivo).join(", ")}</li>}
              {c.avisos.slice(0, 12).map(a => <li key={a}>{a}</li>)}
              {c.avisos.length > 12 && <li>… e mais {c.avisos.length - 12}</li>}
            </Box>
          </Alert>
        )}
        <Secao titulo="Ensaios desta coleta">
          <TabelaEnsaios itens={c.ensaios || []} aoMudar={recarregar} />
        </Secao>
      </Stack>
      <Confirmar aberto={confirmar} perigo titulo="Apagar coleta?" acao="Apagar" aoFechar={() => setConfirmar(false)} aoConfirmar={apagar}
                 texto={`A coleta "${c.descricao || c.id}" e os ${c.n_ensaios} ensaios dela saem da base. Isto não pode ser desfeito.`} />
    </>
  );
}
