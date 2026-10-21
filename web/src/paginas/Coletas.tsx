import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { data } from "../formato";
import { NOME_CONJUNTO, type Coleta } from "../tipos";
import { useCarregar } from "../usar";

export default function Coletas() {
  const { pode } = useAuth();
  const { dados, erro } = useCarregar<Coleta[]>("/api/coletas");
  return (
    <>
      <div className="cabecalho">
        <div><h1>Coletas</h1><p>Cada envio de voltamogramas das empresas, com quem enviou e quando.</p></div>
        {pode("editar") && <Link className="btn prim" to="/coletas/nova">Nova coleta</Link>}
      </div>
      {erro && <div className="erro">{erro}</div>}
      <div className="cartao tabela">
        <table>
          <thead><tr><th>Coleta</th><th>Empresa</th><th>Data</th><th>Conjunto</th><th className="num">Amostras</th>
            <th className="num">Medições</th><th className="num">Sem resultado</th><th>Enviada por</th></tr></thead>
          <tbody>
            {dados?.map(c => (
              <tr key={c.id}>
                <td><Link to={`/coletas/${c.id}`}>{c.descricao || `Coleta #${c.id}`}</Link></td>
                <td>{c.empresa || <span className="mudo">—</span>}</td>
                <td>{data(c.data_coleta || c.criado_em)}</td>
                <td>{NOME_CONJUNTO[c.conjunto || ""]}</td>
                <td className="num">{c.n_amostras}</td><td className="num">{c.n_medicoes}</td>
                <td className="num">{c.amostras_sem_rotulo ? <span className="chip rep">{c.amostras_sem_rotulo}</span> : 0}</td>
                <td>{c.criado_por || <span className="mudo">importação</span>}</td>
              </tr>
            ))}
            {dados && !dados.length && <tr><td colSpan={8} className="vazio">Nenhuma coleta ainda.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}
