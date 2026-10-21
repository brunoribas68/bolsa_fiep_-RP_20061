import { useSearchParams } from "react-router-dom";
import TabelaAmostras from "../componentes/TabelaAmostras";
import type { AmostraLinha, Empresa } from "../tipos";
import { useCarregar } from "../usar";

export default function Amostras() {
  const [p, setP] = useSearchParams();
  const pagina = Number(p.get("pagina") || 1);
  const qs = new URLSearchParams({ ...Object.fromEntries(p), por_pagina: "50" }).toString();
  const { dados, erro, setDados } = useCarregar<{ total: number; itens: AmostraLinha[]; por_pagina: number }>(`/api/amostras?${qs}`);
  const { dados: empresas } = useCarregar<Empresa[]>("/api/empresas");
  const filtro = (k: string, v: string) => {
    const n = new URLSearchParams(p);
    if (v) n.set(k, v); else n.delete(k);
    n.delete("pagina");
    setP(n);
  };
  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.por_pagina)) : 1;
  return (
    <>
      <div className="cabecalho"><div><h1>Amostras</h1>
        <p>Banco de voltamogramas. Complete aqui o resultado do plaqueamento de cada amostra.</p></div></div>
      <div className="cartao">
        <div className="filtros">
          <label className="campo">Buscar código
            <input defaultValue={p.get("q") || ""} placeholder="ex.: EC_01"
                   onKeyDown={e => e.key === "Enter" && filtro("q", (e.target as HTMLInputElement).value)}
                   onBlur={e => e.target.value !== (p.get("q") || "") && filtro("q", e.target.value)} />
          </label>
          <label className="campo">Empresa
            <select value={p.get("empresa_id") || ""} onChange={e => filtro("empresa_id", e.target.value)}>
              <option value="">Todas</option>{empresas?.map(e => <option key={e.id} value={e.id}>{e.nome}</option>)}
            </select>
          </label>
          <label className="campo">Plaqueamento
            <select value={p.get("rotulo") || ""} onChange={e => filtro("rotulo", e.target.value)}>
              <option value="">Todos</option><option value="1">Contaminadas</option>
              <option value="0">Não contaminadas</option><option value="sem">Sem resultado</option>
            </select>
          </label>
          <label className="campo">Uso
            <select value={p.get("conjunto") || ""} onChange={e => filtro("conjunto", e.target.value)}>
              <option value="">Todos</option><option value="sorteio">Sorteio</option><option value="treino">Treino</option>
              <option value="validacao">Validação</option><option value="teste">Teste</option>
            </select>
          </label>
        </div>
        {erro && <div className="erro">{erro}</div>}
        {dados && <TabelaAmostras itens={dados.itens}
          aoMudar={n => setDados(d => d && { ...d, itens: d.itens.map(x => (x.sample_id === n.sample_id ? n : x)) })} />}
        {dados && (
          <div className="paginacao">
            <span>{dados.total} amostras · página {pagina} de {paginas}</span>
            <button className="btn peq" disabled={pagina <= 1} onClick={() => { const n = new URLSearchParams(p); n.set("pagina", String(pagina - 1)); setP(n); }}>Anterior</button>
            <button className="btn peq" disabled={pagina >= paginas} onClick={() => { const n = new URLSearchParams(p); n.set("pagina", String(pagina + 1)); setP(n); }}>Próxima</button>
          </div>
        )}
      </div>
    </>
  );
}
