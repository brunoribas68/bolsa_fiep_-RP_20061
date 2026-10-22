import DeleteOutline from "@mui/icons-material/DeleteOutline";
import InsertDriveFileOutlined from "@mui/icons-material/InsertDriveFileOutlined";
import { Alert, AlertTitle, Box, Button, Chip, Skeleton, Stack } from "@mui/material";
import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAvisos } from "../componentes/avisos";
import { Cabecalho, Kpi, Secao } from "../componentes/comum";
import Confirmar from "../componentes/Confirmar";
import TabelaAmostras from "../componentes/TabelaAmostras";
import { data } from "../formato";
import { NOME_CONJUNTO, type AmostraLinha, type Coleta } from "../tipos";
import { useCarregar } from "../usar";

export default function ColetaDetalhe() {
  const { id } = useParams();
  const local = useLocation();
  const navegar = useNavigate();
  const avisar = useAvisos();
  const { pode } = useAuth();
  const [confirmar, setConfirmar] = useState(false);
  const { dados: c, erro } = useCarregar<Coleta>(`/api/coletas/${id}`);
  const am = useCarregar<{ total: number; itens: AmostraLinha[] }>(`/api/amostras?coleta_id=${id}&por_pagina=200`);

  async function apagar() {
    setConfirmar(false);
    try { await api.del(`/api/coletas/${c!.id}`); avisar("Coleta apagada."); navegar("/coletas"); }
    catch (e) { avisar((e as Error).message, "error"); }
  }

  if (erro) return <Alert severity="error">{erro}</Alert>;
  if (!c) return <Skeleton variant="rounded" height={300} />;
  const incompletas = (c.replicas || []).filter(r => r.n_aprovadas < 3);
  return (
    <>
      <Cabecalho titulo={c.descricao || `Coleta #${c.id}`}
                 sub={`${c.empresa || "Sem empresa"} · ${data(c.data_coleta || c.criado_em)} · enviada por ${c.criado_por || "importação"} em ${data(c.criado_em, true)}`}
                 acoes={pode("admin") && <Button color="error" variant="outlined" startIcon={<DeleteOutline />} onClick={() => setConfirmar(true)}>Apagar coleta</Button>} />
      <Stack spacing={2}>
        {(local.state as { criada?: boolean })?.criada && (
          <Alert severity="success">Coleta recebida: {c.n_amostras} amostras e {c.n_medicoes} medições gravadas no banco.</Alert>)}
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fit, minmax(min(180px, 100%), 1fr))" }}>
          <Kpi rotulo="Amostras" valor={c.n_amostras} />
          <Kpi rotulo="Medições" valor={c.n_medicoes} />
          <Kpi rotulo="Sem resultado" valor={c.amostras_sem_rotulo} cor={c.amostras_sem_rotulo ? "warning.main" : undefined} />
          <Kpi rotulo="Uso no treino" valor={<Box component="span" sx={{ fontSize: 18 }}>{NOME_CONJUNTO[c.conjunto || ""]}</Box>} />
        </Box>
        {(c.avisos.length > 0 || incompletas.length > 0) && (
          <Alert severity="warning"><AlertTitle>Atenção</AlertTitle>
            <Box component="ul" sx={{ m: 0, pl: 2 }}>
              {incompletas.slice(0, 8).map(r => (
                <li key={`${r.sample_id}-${r.replicate_id}`}>{r.sample_id}, eletrodo {r.replicate_id}: {r.n_aprovadas} de 3 etapas aprovadas ({r.estagios || "nenhuma"})</li>))}
              {incompletas.length > 8 && <li>… e mais {incompletas.length - 8} eletrodos incompletos</li>}
              {c.avisos.slice(0, 8).map(a => <li key={a}>{a}</li>)}
            </Box>
          </Alert>
        )}
        <Secao titulo="Amostras">
          {am.dados ? <TabelaAmostras itens={am.dados.itens} mostrarEmpresa={false}
            aoMudar={n => am.setDados(d => d && { ...d, itens: d.itens.map(x => (x.sample_id === n.sample_id ? n : x)) })} />
            : <Skeleton variant="rounded" height={120} />}
        </Secao>
        {c.arquivos && c.arquivos.length > 0 && (
          <Secao titulo={`Arquivos recebidos (${c.arquivos.length})`}>
            <Stack direction="row" spacing={.75} flexWrap="wrap" useFlexGap>
              {c.arquivos.map(a => <Chip key={a.sha256} size="small" variant="outlined" icon={<InsertDriveFileOutlined />}
                                         label={a.arquivo} title={`SHA-256 ${a.sha256}…`} sx={{ fontFamily: "monospace" }} />)}
            </Stack>
          </Secao>
        )}
      </Stack>
      <Confirmar aberto={confirmar} perigo titulo="Apagar coleta?" acao="Apagar" aoFechar={() => setConfirmar(false)} aoConfirmar={apagar}
                 texto={`A coleta "${c.descricao || c.id}" e as ${c.n_amostras} amostras dela serão apagadas. Isto não pode ser desfeito.`} />
    </>
  );
}
