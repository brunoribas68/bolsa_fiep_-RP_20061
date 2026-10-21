import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { entrar } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setErro(""); setEnviando(true);
    try { await entrar(email, senha); }
    catch (er) { setErro((er as Error).message); setSenha(""); }
    finally { setEnviando(false); }
  }

  return (
    <div className="tela-login">
      <div className="cartao">
        <div className="marca" style={{ padding: 0 }}>
          <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="var(--primaria)" />
            <path d="M5 20c4 0 5-9 9-9s4 11 8 11 4-6 5-6" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" /></svg>
          <div>Plataforma FIEP<small>Monitoramento microbiológico por voltametria</small></div>
        </div>
        <form onSubmit={enviar}>
          <label className="campo">E-mail
            <input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} autoFocus />
          </label>
          <label className="campo">Senha
            <input type="password" autoComplete="current-password" required value={senha} onChange={e => setSenha(e.target.value)} />
          </label>
          {erro && <div className="erro" role="alert">{erro}</div>}
          <button className="btn prim" disabled={enviando} style={{ justifyContent: "center" }}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
          <p className="mudo pequeno" style={{ margin: 0 }}>
            Não tem acesso? Peça ao administrador do projeto para criar sua conta.
          </p>
        </form>
      </div>
    </div>
  );
}
