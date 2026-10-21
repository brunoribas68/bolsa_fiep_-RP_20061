import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import TabelaAmostras from "../componentes/TabelaAmostras";
import { data } from "../formato";
import { NOME_CONJUNTO, type AmostraLinha, type Coleta } from "../tipos";
import { useCarregar } from "../usar";

export default function ColetaDetalhe() {
  const { id } = useParams();
  const local = useLocation();
  const navegar = useNavigate();
  const { pode } = useAuth();
  const { dados: c, erro } = useCarregar<Coleta>(`/api/coletas/${id}`);
  const am = useCarregar<{ total: number; itens: AmostraLinha[] }>(`/api/amostras?coleta_id=${id}&por_pagina=200`);

  async function apagar() {
    if (!c || !window.confirm(`Apagar a coleta "${c.descricao || c.id}" e as ${c.n_amostras} amostras dela? Isto não pode ser desfeito.`)) return;
    await api.del(`/api/coletas/${c.id}`);
    navegar("/coletas");
  }

  if (erro) return <div className="erro">{erro}</div>;
  if (!c) return <div className="mudo">Carregando…</div>;
  const incompletas = (c.replicas || []).filter(r => r.n_aprovadas < 3);
  return (
    <>
      <div className="cabecalho">
        <div><h1>{c.descricao || `Coleta #${c.id}`}</h1>
          <p>{c.empresa || "Sem empresa"} · {data(c.data_coleta || c.criado_em)} · enviada por {c.criado_por || "importação"} em {data(c.criado_em, true)}</p></div>
        {pode("admin") && <button className="btn perigo" onClick={apagar}>Apagar coleta</button>}
      </div>
      <div className="pilha">
        {(local.state as { criada?: boolean })?.criada && (
          <div className="ok">Coleta recebida: {c.n_amostras} amostras e {c.n_medicoes} medições gravadas no banco.</div>)}
        <div className="grade grade-kpi">
          <div className="kpi"><div className="rot">Amostras</div><div className="val">{c.n_amostras}</div></div>
          <div className="kpi"><div className="rot">Medições</div><div className="val">{c.n_medicoes}</div></div>
          <div className="kpi"><div className="rot">Sem resultado</div><div className="val">{c.amostras_sem_rotulo}</div></div>
          <div className="kpi"><div className="rot">Uso no treino</div><div className="val" style={{ fontSize: 17 }}>{NOME_CONJUNTO[c.conjunto || ""]}</div></div>
        </div>
        {(c.avisos.length > 0 || incompletas.length > 0) && (
          <div className="aviso"><strong>Atenção</strong><ul>
            {incompletas.slice(0, 8).map(r => (
              <li key={`${r.sample_id}-${r.replicate_id}`}>{r.sample_id}, réplica {r.replicate_id}: {r.n_aprovadas} de 3 estágios aprovados ({r.estagios || "nenhum"})</li>))}
            {incompletas.length > 8 && <li>… e mais {incompletas.length - 8} réplicas incompletas</li>}
            {c.avisos.slice(0, 8).map(a => <li key={a}>{a}</li>)}
          </ul></div>
        )}
        <div className="cartao">
          <h2>Amostras</h2>
          {am.dados && <TabelaAmostras itens={am.dados.itens} mostrarEmpresa={false}
            aoMudar={n => am.setDados(d => d && { ...d, itens: d.itens.map(x => (x.sample_id === n.sample_id ? n : x)) })} />}
        </div>
        {c.arquivos && c.arquivos.length > 0 && (
          <div className="cartao">
            <h2>Arquivos recebidos ({c.arquivos.length})</h2>
            <div className="arquivos">{c.arquivos.map(a => <span className="arquivo" key={a.sha256} title={`SHA-256 ${a.sha256}…`}>{a.arquivo}</span>)}</div>
          </div>
        )}
      </div>
    </>
  );
}
