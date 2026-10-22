import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import GraficoCurvas, { type Serie } from "../componentes/GraficoCurvas";
import { BarraProb, ChipResultado, ChipRotulo, SeloQC } from "../componentes/rotulos";
import { data, num, pct } from "../formato";
import { NOME_CONJUNTO, NOME_ESTAGIO, type AmostraDetalhe as Det, type Curva, type PrevisaoAmostra, type PrevisaoReplica, type Protocolo } from "../tipos";
import { useCarregar } from "../usar";

const CORES = ["var(--serie-1)", "var(--serie-2)", "var(--serie-3)"];

function Edicao({ a, aoSalvar }: { a: Det; aoSalvar: (d: Det) => void }) {
  const [f, setF] = useState({
    contamination_status: a.contamination_status === null ? "" : String(a.contamination_status),
    sample_log10_mean_cfu_ml: a.sample_log10_mean_cfu_ml === null ? "" : String(a.sample_log10_mean_cfu_ml),
    target_bacterium: a.target_bacterium || "", surface_type: a.surface_type || "",
    conjunto: a.conjunto || "", observacoes: a.observacoes || "",
  });
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const mudar = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  async function salvar() {
    setMsg(null);
    const carga = f.sample_log10_mean_cfu_ml.trim().replace(",", ".");
    try {
      const d = await api.patch<Det>(`/api/amostras/${encodeURIComponent(a.sample_id)}`, {
        contamination_status: f.contamination_status === "" ? null : Number(f.contamination_status),
        sample_log10_mean_cfu_ml: carga === "" ? null : Number(carga),
        target_bacterium: f.target_bacterium, surface_type: f.surface_type,
        conjunto: f.conjunto || null, observacoes: f.observacoes,
      });
      aoSalvar(d); setMsg({ ok: true, t: "Alterações salvas." });
    } catch (e) { setMsg({ ok: false, t: (e as Error).message }); }
  }
  return (
    <div className="pilha">
      <div className="linha-campos">
        <label className="campo">Resultado do plaqueamento
          <select value={f.contamination_status} onChange={mudar("contamination_status")}>
            <option value="">Sem resultado</option><option value="1">Contaminada</option><option value="0">Não contaminada</option>
          </select></label>
        <label className="campo">Carga <small>log₁₀ UFC/mL</small>
          <input inputMode="decimal" value={f.sample_log10_mean_cfu_ml} onChange={mudar("sample_log10_mean_cfu_ml")} /></label>
        <label className="campo">Bactéria alvo<input value={f.target_bacterium} onChange={mudar("target_bacterium")} /></label>
        <label className="campo">Superfície<input value={f.surface_type} onChange={mudar("surface_type")} placeholder="ex.: aço inox, esteira" /></label>
        <label className="campo">Uso no treino
          <select value={f.conjunto} onChange={mudar("conjunto")}>
            {Object.entries(NOME_CONJUNTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
      </div>
      <label className="campo">Observações<textarea value={f.observacoes} onChange={mudar("observacoes")} maxLength={2000} /></label>
      <div className="acoes"><button className="btn prim" onClick={salvar}>Salvar</button>
        {msg && <span className={msg.ok ? "ok" : "erro"}>{msg.t}</span>}</div>
    </div>
  );
}

export default function AmostraDetalhe() {
  const { id = "" } = useParams();
  const { pode } = useAuth();
  const url = `/api/amostras/${encodeURIComponent(id)}`;
  const { dados: a, erro, setDados, recarregar } = useCarregar<Det>(url);
  const { dados: curvas } = useCarregar<Curva[]>(`${url}/curvas`);
  const [replica, setReplica] = useState<string | null>(null);
  const [prev, setPrev] = useState<{ amostra: PrevisaoAmostra | null; replicas: PrevisaoReplica[]; limiar: number } | null>(null);
  const [erroPrev, setErroPrev] = useState("");
  const [prevendo, setPrevendo] = useState(false);

  const { dados: protocolos } = useCarregar<Record<string, Protocolo>>("/api/protocolos");
  // protocolo da amostra: o que tem mais estágios em comum com as medições dela
  const etapas = useMemo(() => {
    const presentes = new Set((a?.medicoes || []).map(m => m.sensor_state));
    const lista = Object.values(protocolos || {});
    const melhor = lista.sort((x, y) => y.estagios.filter(e => presentes.has(e.id)).length
      - x.estagios.filter(e => presentes.has(e.id)).length)[0];
    return melhor ? melhor.estagios : [];
  }, [protocolos, a]);
  const ordem = etapas.map(e => e.id);
  const nomeEst = (id: string | null) => etapas.find(e => e.id === id)?.nome || NOME_ESTAGIO[id || ""] || id || "?";
  const replicas = useMemo(() => [...new Set((curvas || []).map(c => c.replicate_id || "—"))]
    .sort((x, y) => x.localeCompare(y, "pt-BR", { numeric: true })), [curvas]);
  const atual = replica ?? replicas[0] ?? null;
  const series: Serie[] = useMemo(() => (curvas || [])
    .filter(c => (c.replicate_id || "—") === atual)
    .sort((x, y) => ordem.indexOf(x.sensor_state || "") - ordem.indexOf(y.sensor_state || ""))
    .map(c => ({
      nome: `${nomeEst(c.sensor_state)}${c.qc_final && c.qc_final !== "PASS" ? ` (QC ${c.qc_final})` : ""}`,
      cor: CORES[ordem.indexOf(c.sensor_state || "")] || "var(--texto-3)", x: c.potential_v, y: c.current_ua,
      fraca: !!c.qc_final && c.qc_final !== "PASS",
    })), [curvas, atual, etapas]);

  async function prever() {
    setErroPrev(""); setPrevendo(true);
    try { setPrev(await api.post(`${url}/prever`)); recarregar(); }
    catch (e) { setErroPrev((e as Error).message); } finally { setPrevendo(false); }
  }

  async function mudarEstagio(mid: string, sensor_state: string) {
    await api.patch(`/api/medicoes/${encodeURIComponent(mid)}`, { sensor_state });
    recarregar();
  }

  if (erro) return <div className="erro">{erro}</div>;
  if (!a) return <div className="mudo">Carregando…</div>;
  return (
    <>
      <div className="cabecalho">
        <div><h1 className="mono" style={{ fontSize: 22 }}>{a.sample_id}</h1>
          <p>{a.empresa || "Sem empresa"}{a.coleta_id && <> · <Link to={`/coletas/${a.coleta_id}`}>coleta #{a.coleta_id}</Link></>}
            {a.atualizado_por && <> · editada por {a.atualizado_por} em {data(a.atualizado_em, true)}</>}</p></div>
        <div className="acoes"><ChipRotulo v={a.contamination_status} />
          <button className="btn prim" onClick={prever} disabled={prevendo}>{prevendo ? "Calculando…" : "Prever com o modelo"}</button></div>
      </div>
      <div className="pilha">
        {erroPrev && <div className="erro">{erroPrev}</div>}
        {prev?.amostra && (
          <div className="cartao">
            <h2>Previsão do modelo</h2>
            <div className="acoes" style={{ gap: 18 }}>
              <ChipResultado r={prev.amostra.resultado} />
              <div style={{ width: 240 }}><BarraProb p={prev.amostra.prob_contaminada} limiar={prev.limiar} /></div>
              <span>Nível: <strong>{prev.amostra.nivel_contaminacao || "—"}</strong></span>
              <span>Carga estimada: <strong>{num(prev.amostra.log10_ufc_ml_estimado, 1)}</strong> log₁₀ UFC/mL</span>
              <span className="mudo">{prev.amostra.replicas_avaliadas} de {prev.amostra.replicas_total} réplicas avaliadas · {pct(prev.amostra.concordancia)} concordam</span>
            </div>
            {prev.replicas.some(r => r.status !== "avaliada") && (
              <div className="aviso" style={{ marginTop: 12 }}><ul>
                {prev.replicas.filter(r => r.status !== "avaliada").map((r, i) => (
                  <li key={i}>Réplica {r.replicate_id || "?"}: {r.resultado.toLowerCase()} — {r.motivo}</li>))}
              </ul></div>)}
          </div>
        )}
        <div className="cartao">
          <h2>Voltamogramas</h2>
          {replicas.length > 1 && (
            <div className="abas" role="tablist">
              {replicas.map(r => <button key={r} role="tab" aria-selected={r === atual} className={r === atual ? "ativa" : ""}
                                         onClick={() => setReplica(r)}>Eletrodo {r}</button>)}
            </div>)}
          {curvas ? <GraficoCurvas series={series} /> : <div className="mudo">Carregando curvas…</div>}
        </div>
        <div className="grade grade-2">
          <div className="cartao">
            <h2>Dados da amostra</h2>
            {pode("editar") ? <Edicao key={a.atualizado_em} a={a} aoSalvar={setDados} /> : (
              <dl className="dl">
                <dt>Carga</dt><dd>{num(a.sample_log10_mean_cfu_ml, 2)} log₁₀ UFC/mL</dd>
                <dt>Bactéria</dt><dd>{a.target_bacterium || "—"}</dd><dt>Superfície</dt><dd>{a.surface_type || "—"}</dd>
                <dt>Uso</dt><dd>{NOME_CONJUNTO[a.conjunto || ""]}</dd><dt>Observações</dt><dd>{a.observacoes || "—"}</dd>
              </dl>)}
          </div>
          <div className="cartao">
            <h2>Plaqueamento</h2>
            {a.plaqueamentos.length ? (
              <div className="tabela"><table>
                <thead><tr><th>Placa</th><th className="num">Colônias</th><th className="num">UFC/mL</th><th className="num">log₁₀</th></tr></thead>
                <tbody>{a.plaqueamentos.map(p => <tr key={p.replica}><td>{p.replica}</td><td className="num">{num(p.colonias, 0)}</td>
                  <td className="num">{num(p.ufc_ml, 0)}</td><td className="num">{num(p.log10_ufc_ml, 2)}</td></tr>)}</tbody>
              </table></div>) : <p className="mudo">Sem placas registradas. O resultado pode ser informado em “Dados da amostra”.</p>}
            <h2 style={{ marginTop: 18 }}>Histórico de previsões</h2>
            {a.previsoes.filter(p => p.status === "amostra").length ? (
              <div className="tabela"><table><tbody>
                {a.previsoes.filter(p => p.status === "amostra").slice(0, 6).map((p, i) => (
                  <tr key={i}><td><ChipResultado r={p.resultado} /></td><td className="num">{pct(p.prob_contaminada)}</td>
                    <td>{p.nivel || ""}</td><td className="mudo pequeno">{data(p.previsto_em, true)}</td></tr>))}
              </tbody></table></div>) : <p className="mudo">Nenhuma previsão ainda.</p>}
          </div>
        </div>
        <div className="cartao">
          <h2>Medições ({a.medicoes.length})</h2>
          <div className="tabela"><table>
            <thead><tr><th>Eletrodo</th><th>Etapa do sensor</th><th>Técnica</th><th>QC</th><th>Arquivo</th><th className="num">Pontos</th></tr></thead>
            <tbody>{[...a.medicoes].sort((x, y) => String(x.replicate_id).localeCompare(String(y.replicate_id), "pt-BR", { numeric: true })
              || ordem.indexOf(x.sensor_state || "") - ordem.indexOf(y.sensor_state || "")).map(m => (
              <tr key={m.measurement_id}>
                <td>{m.replicate_id || "—"}</td>
                <td>{pode("editar") ? (
                  <select value={m.sensor_state || ""} aria-label="Estágio do sensor" onChange={e => mudarEstagio(m.measurement_id, e.target.value)}>
                    {!m.sensor_state && <option value="">— definir —</option>}
                    {etapas.map(s => <option key={s.id} value={s.id}>{s.nome}</option>)}
                  </select>) : nomeEst(m.sensor_state)}</td>
                <td>{m.tecnica}</td>
                <td><SeloQC v={m.qc_final} />{m.qc_motivos && <div className="mudo pequeno">{m.qc_motivos}</div>}</td>
                <td className="mono">{m.arquivo_origem}</td><td className="num">{m.n_pontos}</td>
              </tr>))}</tbody>
          </table></div>
        </div>
      </div>
    </>
  );
}
