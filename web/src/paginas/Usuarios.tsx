import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { data } from "../formato";
import { NOME_PAPEL, type Papel, type Usuario } from "../tipos";
import { useCarregar } from "../usar";

const VAZIO = { nome: "", email: "", senha: "", papel: "colaborador" as Papel, instituicao: "" };

export default function Usuarios() {
  const { usuario: eu } = useAuth();
  const { dados, erro, recarregar } = useCarregar<Usuario[]>("/api/usuarios");
  const [f, setF] = useState(VAZIO);
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);

  async function acao(fn: () => Promise<unknown>, ok: string) {
    setMsg(null);
    try { await fn(); setMsg({ ok: true, t: ok }); recarregar(); }
    catch (e) { setMsg({ ok: false, t: (e as Error).message }); }
  }
  const criar = () => acao(async () => { await api.post("/api/usuarios", f); setF(VAZIO); }, `Conta de ${f.email} criada.`);
  const redefinir = (u: Usuario) => {
    const nova = window.prompt(`Nova senha para ${u.email} (mínimo 10 caracteres):`);
    if (nova) acao(() => api.post(`/api/usuarios/${u.id}/senha`, { nova }), `Senha de ${u.email} redefinida.`);
  };
  return (
    <>
      <div className="cabecalho"><div><h1>Usuários</h1>
        <p>Só administradores criam contas. Colaboradores enviam e editam dados; leitores só consultam.</p></div></div>
      <div className="pilha">
        <div className="cartao">
          <h2>Nova conta</h2>
          <div className="linha-campos">
            <label className="campo">Nome<input value={f.nome} onChange={e => setF({ ...f, nome: e.target.value })} /></label>
            <label className="campo">E-mail<input type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoComplete="off" /></label>
            <label className="campo">Senha inicial <small>mín. 10 caracteres</small>
              <input type="password" value={f.senha} onChange={e => setF({ ...f, senha: e.target.value })} autoComplete="new-password" /></label>
            <label className="campo">Perfil
              <select value={f.papel} onChange={e => setF({ ...f, papel: e.target.value as Papel })}>
                {Object.entries(NOME_PAPEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></label>
            <label className="campo">Instituição<input value={f.instituicao} onChange={e => setF({ ...f, instituicao: e.target.value })} /></label>
          </div>
          <div className="acoes" style={{ marginTop: 12 }}>
            <button className="btn prim" disabled={!f.nome || !f.email || f.senha.length < 10} onClick={criar}>Criar conta</button>
            {msg && <span className={msg.ok ? "ok" : "erro"}>{msg.t}</span>}
          </div>
        </div>
        {erro && <div className="erro">{erro}</div>}
        <div className="cartao tabela"><table>
          <thead><tr><th>Nome</th><th>E-mail</th><th>Perfil</th><th>Instituição</th><th>Último acesso</th><th>Situação</th><th /></tr></thead>
          <tbody>{dados?.map(u => (
            <tr key={u.id}>
              <td>{u.nome}{u.id === eu?.id && <span className="mudo"> (você)</span>}</td><td>{u.email}</td>
              <td><select value={u.papel} aria-label={`Perfil de ${u.nome}`}
                          onChange={e => acao(() => api.patch(`/api/usuarios/${u.id}`, { papel: e.target.value }), "Perfil alterado.")}>
                {Object.entries(NOME_PAPEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
              <td>{u.instituicao || "—"}</td><td>{data(u.ultimo_login, true)}</td>
              <td>{u.ativo ? <span className="chip c0">Ativo</span> : <span className="chip sem">Desativado</span>}</td>
              <td><div className="acoes">
                <button className="btn peq" onClick={() => redefinir(u)}>Redefinir senha</button>
                <button className={`btn peq${u.ativo ? " perigo" : ""}`}
                        onClick={() => acao(() => api.patch(`/api/usuarios/${u.id}`, { ativo: !u.ativo }), u.ativo ? "Conta desativada." : "Conta reativada.")}>
                  {u.ativo ? "Desativar" : "Reativar"}</button></div></td>
            </tr>))}</tbody></table></div>
      </div>
    </>
  );
}
