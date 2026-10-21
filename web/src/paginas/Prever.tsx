import { useState } from "react";
import { api, baixar } from "../api";
import Soltar, { type ArquivoComCaminho } from "../componentes/Soltar";
import { BarraProb, ChipResultado } from "../componentes/rotulos";
import { num, pct } from "../formato";
import type { PrevisaoAmostra, PrevisaoReplica } from "../tipos";

interface Resposta { modelo: string; algoritmo: string; limiar: number; amostras: PrevisaoAmostra[];
  resultados: PrevisaoReplica[]; avisos: string[] }

export default function Prever() {
  const [arquivos, setArquivos] = useState<ArquivoComCaminho[]>([]);
  const [res, setRes] = useState<Resposta | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const fd = () => {
    const f = new FormData();
    arquivos.forEach(a => { f.append("arquivos", a.arquivo, a.arquivo.name); f.append("caminhos", a.caminho); });
    return f;
  };
  async function analisar() {
    setErro(""); setOcupado(true);
    try { setRes(await api.post<Resposta>("/api/prever", fd())); }
    catch (e) { setErro((e as Error).message); } finally { setOcupado(false); }
  }
  async function excel() {
    setErro("");
    try { baixar(await api.post<Blob>("/api/excel", fd()), "voltamogramas_excel.zip"); }
    catch (e) { setErro((e as Error).message); }
  }

  return (
    <>
      <div className="cabecalho"><div><h1>Previsão rápida</h1>
        <p>Classifica voltamogramas sem gravar no banco. Para guardar os dados, use <b>Nova coleta</b>.</p></div></div>
      <div className="pilha">
        <div className="cartao">
          <Soltar aoReceber={l => { setArquivos(a => [...a, ...l]); setRes(null); }} titulo="Arraste arquivos ou a pasta das amostras"
                  dica=".nox ou Excel/CSV do NOVA. Uma subpasta por amostra; sem pastas, o envio inteiro é uma amostra." />
          {arquivos.length > 0 && (
            <div className="arquivos">{arquivos.map((a, i) => (
              <span className="arquivo" key={i}>{a.caminho}
                <button aria-label={`remover ${a.caminho}`} onClick={() => setArquivos(l => l.filter((_, j) => j !== i))}>×</button></span>))}
            </div>)}
          <div className="acoes" style={{ marginTop: 12 }}>
            <button className="btn prim" disabled={!arquivos.length || ocupado} onClick={analisar}>{ocupado ? "Analisando…" : "Analisar"}</button>
            <button className="btn" disabled={!arquivos.some(a => /\.nox$/i.test(a.arquivo.name))} onClick={excel}>Converter .nox para Excel</button>
            {arquivos.length > 0 && <button className="btn link" onClick={() => { setArquivos([]); setRes(null); }}>Limpar</button>}
          </div>
          {erro && <div className="erro" style={{ marginTop: 10 }}>{erro}</div>}
        </div>
        {res && (
          <div className="cartao">
            <h2>Resultado por amostra</h2>
            <p className="mudo pequeno" style={{ marginTop: -6 }}>Modelo {res.algoritmo} · a barra mostra o limiar de decisão ({pct(res.limiar)}).</p>
            <div className="tabela"><table>
              <thead><tr><th>Amostra</th><th>Resultado</th><th>Prob. contaminada</th><th>Nível</th>
                <th className="num">Carga estimada (log₁₀ UFC/mL)</th><th>Réplicas</th></tr></thead>
              <tbody>{res.amostras.map(a => (
                <tr key={a.sample_id}><td className="mono">{a.sample_id}</td><td><ChipResultado r={a.resultado} /></td>
                  <td><BarraProb p={a.prob_contaminada} limiar={res.limiar} /></td><td>{a.nivel_contaminacao || "—"}</td>
                  <td className="num">{num(a.log10_ufc_ml_estimado, 1)}</td>
                  <td className="mudo pequeno">{a.replicas_avaliadas} de {a.replicas_total} avaliadas{a.concordancia !== null && ` · ${pct(a.concordancia)} concordam`}</td></tr>))}
                {!res.amostras.length && <tr><td colSpan={6} className="vazio">Nenhuma amostra identificada.</td></tr>}
              </tbody></table></div>
            <details style={{ marginTop: 12 }}><summary className="mudo">Detalhe por réplica (eletrodo)</summary>
              <div className="tabela"><table>
                <thead><tr><th>Amostra</th><th>Réplica</th><th>Resultado</th><th>Prob.</th><th>Observação</th></tr></thead>
                <tbody>{res.resultados.map((r, i) => (
                  <tr key={i}><td className="mono">{r.sample_id || "—"}</td><td>{r.replicate_id || "—"}</td>
                    <td><ChipResultado r={r.resultado} /></td><td>{pct(r.prob_contaminada)}</td><td className="mudo pequeno">{r.motivo}</td></tr>))}
                </tbody></table></div></details>
            {res.avisos.length > 0 && <div className="aviso" style={{ marginTop: 12 }}><ul>{res.avisos.slice(0, 10).map(a => <li key={a}>{a}</li>)}</ul></div>}
          </div>
        )}
      </div>
    </>
  );
}
