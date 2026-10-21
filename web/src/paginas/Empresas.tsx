import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Empresa } from "../tipos";
import { useCarregar } from "../usar";

const VAZIA = { nome: "", cidade: "", segmento: "", observacoes: "" };

export default function Empresas() {
  const { pode } = useAuth();
  const { dados, erro, recarregar } = useCarregar<Empresa[]>("/api/empresas");
  const [f, setF] = useState(VAZIA);
  const [editando, setEditando] = useState<number | null>(null);
  const [msg, setMsg] = useState("");

  async function salvar() {
    setMsg("");
    try {
      if (editando) await api.patch(`/api/empresas/${editando}`, f);
      else await api.post("/api/empresas", f);
      setF(VAZIA); setEditando(null); recarregar();
    } catch (e) { setMsg((e as Error).message); }
  }
  return (
    <>
      <div className="cabecalho"><div><h1>Empresas</h1><p>Empresas validadoras onde as coletas são feitas.</p></div></div>
      <div className="pilha">
        {pode("editar") && (
          <div className="cartao">
            <h2>{editando ? "Editar empresa" : "Cadastrar empresa"}</h2>
            <div className="linha-campos">
              <label className="campo">Nome<input value={f.nome} onChange={e => setF({ ...f, nome: e.target.value })} maxLength={160} /></label>
              <label className="campo">Cidade<input value={f.cidade} onChange={e => setF({ ...f, cidade: e.target.value })} /></label>
              <label className="campo">Segmento<input value={f.segmento} onChange={e => setF({ ...f, segmento: e.target.value })} placeholder="ex.: laticínios" /></label>
            </div>
            <div className="acoes" style={{ marginTop: 12 }}>
              <button className="btn prim" disabled={!f.nome.trim()} onClick={salvar}>{editando ? "Salvar" : "Cadastrar"}</button>
              {editando && <button className="btn" onClick={() => { setEditando(null); setF(VAZIA); }}>Cancelar</button>}
              {msg && <span className="erro">{msg}</span>}
            </div>
          </div>)}
        {erro && <div className="erro">{erro}</div>}
        <div className="cartao tabela"><table>
          <thead><tr><th>Empresa</th><th>Cidade</th><th>Segmento</th><th className="num">Coletas</th><th className="num">Amostras</th><th /></tr></thead>
          <tbody>{dados?.map(e => (
            <tr key={e.id}><td>{e.nome}</td><td>{e.cidade || "—"}</td><td>{e.segmento || "—"}</td>
              <td className="num">{e.n_coletas}</td><td className="num"><Link to={`/amostras?empresa_id=${e.id}`}>{e.n_amostras}</Link></td>
              <td>{pode("editar") && <button className="btn peq" onClick={() => { setEditando(e.id);
                setF({ nome: e.nome, cidade: e.cidade || "", segmento: e.segmento || "", observacoes: e.observacoes || "" }); }}>Editar</button>}</td></tr>))}
            {dados && !dados.length && <tr><td colSpan={6} className="vazio">Nenhuma empresa cadastrada.</td></tr>}
          </tbody></table></div>
      </div>
    </>
  );
}
