import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { data, num, pct } from "../formato";
import { useCarregar } from "../usar";

interface PainelDados {
  amostras: number; contaminadas: number; nao_contaminadas: number; sem_rotulo: number; medicoes: number;
  replicas_completas: number; replicas: number; reprovadas_qc: number; empresas: number; coletas: number;
  por_empresa: { empresa: string; contaminadas: number; nao_contaminadas: number; sem_rotulo: number }[];
  coletas_recentes: { id: number; descricao: string | null; criado_em: string; n_amostras: number; empresa: string | null; criado_por: string | null }[];
  modelo: { id: string; algoritmo: string; limiar: number; ab_teste: number | null; auc_teste: number | null; n_amostras: number } | null;
}

export default function Painel() {
  const { usuario, pode } = useAuth();
  const { dados: d, erro } = useCarregar<PainelDados>("/api/painel");
  return (
    <>
      <div className="cabecalho">
        <div><h1>Olá, {usuario?.nome.split(" ")[0]}</h1><p>Situação do banco de voltamogramas e do modelo em uso.</p></div>
        {pode("editar") && <Link className="btn prim" to="/coletas/nova">Nova coleta</Link>}
      </div>
      {erro && <div className="erro">{erro}</div>}
      {d && (
        <div className="pilha">
          <div className="grade grade-kpi">
            <div className="kpi"><div className="rot">Amostras</div><div className="val">{d.amostras}</div>
              <div className="sub">{d.empresas} empresas · {d.coletas} coletas</div></div>
            <div className="kpi"><div className="rot">Contaminadas</div><div className="val">{d.contaminadas}</div>
              <div className="sub">{d.nao_contaminadas} não contaminadas</div></div>
            <div className="kpi"><div className="rot">Sem resultado de plaqueamento</div><div className="val">{d.sem_rotulo}</div>
              <div className="sub">{d.sem_rotulo ? <Link to="/amostras?rotulo=sem">completar rótulos</Link> : "tudo rotulado"}</div></div>
            <div className="kpi"><div className="rot">Réplicas completas</div><div className="val">{d.replicas_completas}</div>
              <div className="sub">de {d.replicas} · {d.reprovadas_qc} medições reprovadas no QC</div></div>
          </div>
          <div className="grade grade-2">
            <div className="cartao">
              <h2>Modelo em uso</h2>
              {d.modelo ? (
                <dl className="dl">
                  <dt>Modelo</dt><dd>{d.modelo.algoritmo}</dd>
                  <dt>Registro</dt><dd className="mono">{d.modelo.id}</dd>
                  <dt>Acurácia balanceada (teste)</dt><dd>{num(d.modelo.ab_teste, 3)}</dd>
                  <dt>AUC (teste)</dt><dd>{num(d.modelo.auc_teste, 3)}</dd>
                  <dt>Limiar de decisão</dt><dd>{pct(d.modelo.limiar)}</dd>
                  <dt>Amostras no treino</dt><dd>{d.modelo.n_amostras}</dd>
                </dl>
              ) : <p className="mudo">Nenhum modelo treinado ainda. Rode <code>fiep experimento</code> com os dados do banco.</p>}
            </div>
            <div className="cartao">
              <h2>Coletas recentes</h2>
              {d.coletas_recentes.length ? (
                <div className="tabela"><table><tbody>
                  {d.coletas_recentes.map(c => (
                    <tr key={c.id}>
                      <td><Link to={`/coletas/${c.id}`}>{c.descricao || `Coleta #${c.id}`}</Link>
                        <div className="mudo pequeno">{c.empresa || "sem empresa"} · {c.criado_por || "importação"}</div></td>
                      <td className="num">{c.n_amostras} amostras</td>
                      <td className="num mudo">{data(c.criado_em)}</td>
                    </tr>))}
                </tbody></table></div>
              ) : <p className="mudo">Nenhuma coleta ainda.</p>}
            </div>
          </div>
          <div className="cartao">
            <h2>Amostras por empresa</h2>
            <div className="tabela"><table>
              <thead><tr><th>Empresa</th><th className="num">Contaminadas</th><th className="num">Não contaminadas</th>
                <th className="num">Sem resultado</th><th style={{ width: "34%" }}>Distribuição</th></tr></thead>
              <tbody>{d.por_empresa.map(e => {
                const t = e.contaminadas + e.nao_contaminadas + e.sem_rotulo || 1;
                return (
                  <tr key={e.empresa}>
                    <td>{e.empresa}</td><td className="num">{e.contaminadas}</td><td className="num">{e.nao_contaminadas}</td>
                    <td className="num">{e.sem_rotulo}</td>
                    <td><div style={{ display: "flex", height: 8, gap: 2 }} aria-hidden="true">
                      <span style={{ flex: e.contaminadas / t, background: "var(--contaminada)", borderRadius: 3 }} />
                      <span style={{ flex: e.nao_contaminadas / t, background: "var(--limpa)", borderRadius: 3 }} />
                      <span style={{ flex: e.sem_rotulo / t, background: "var(--borda-forte)", borderRadius: 3 }} />
                    </div></td>
                  </tr>);
              })}
              {!d.por_empresa.length && <tr><td colSpan={5} className="vazio">Sem amostras.</td></tr>}
              </tbody></table></div>
          </div>
        </div>
      )}
    </>
  );
}
