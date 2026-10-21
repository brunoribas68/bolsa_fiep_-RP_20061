import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { NOME_PAPEL } from "../tipos";

export default function Conta() {
  const { usuario } = useAuth();
  const [f, setF] = useState({ atual: "", nova: "", repetir: "" });
  const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  async function trocar() {
    setMsg(null);
    if (f.nova !== f.repetir) return setMsg({ ok: false, t: "As senhas novas não conferem." });
    try {
      await api.post("/api/auth/senha", { atual: f.atual, nova: f.nova });
      setF({ atual: "", nova: "", repetir: "" });
      setMsg({ ok: true, t: "Senha alterada. As sessões abertas em outros computadores foram encerradas." });
    } catch (e) { setMsg({ ok: false, t: (e as Error).message }); }
  }
  return (
    <>
      <div className="cabecalho"><div><h1>Minha conta</h1></div></div>
      <div className="grade grade-2">
        <div className="cartao"><h2>Perfil</h2>
          <dl className="dl"><dt>Nome</dt><dd>{usuario?.nome}</dd><dt>E-mail</dt><dd>{usuario?.email}</dd>
            <dt>Perfil</dt><dd>{usuario && NOME_PAPEL[usuario.papel]}</dd><dt>Instituição</dt><dd>{usuario?.instituicao || "—"}</dd></dl></div>
        <div className="cartao"><h2>Trocar senha</h2>
          <div className="pilha">
            <label className="campo">Senha atual<input type="password" autoComplete="current-password" value={f.atual} onChange={e => setF({ ...f, atual: e.target.value })} /></label>
            <label className="campo">Nova senha <small>mínimo 10 caracteres</small><input type="password" autoComplete="new-password" value={f.nova} onChange={e => setF({ ...f, nova: e.target.value })} /></label>
            <label className="campo">Repita a nova senha<input type="password" autoComplete="new-password" value={f.repetir} onChange={e => setF({ ...f, repetir: e.target.value })} /></label>
            <div className="acoes"><button className="btn prim" disabled={!f.atual || f.nova.length < 10} onClick={trocar}>Trocar senha</button></div>
            {msg && <div className={msg.ok ? "ok" : "erro"}>{msg.t}</div>}
          </div></div>
      </div>
    </>
  );
}
