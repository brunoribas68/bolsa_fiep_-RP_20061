import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { IcAmostra, IcColeta, IcConta, IcEmpresa, IcPainel, IcPrever, IcSair, IcUsuarios } from "./componentes/icones";
import Amostras from "./paginas/Amostras";
import AmostraDetalhe from "./paginas/AmostraDetalhe";
import ColetaDetalhe from "./paginas/ColetaDetalhe";
import Coletas from "./paginas/Coletas";
import Conta from "./paginas/Conta";
import Empresas from "./paginas/Empresas";
import Login from "./paginas/Login";
import NovaColeta from "./paginas/NovaColeta";
import Painel from "./paginas/Painel";
import Prever from "./paginas/Prever";
import Usuarios from "./paginas/Usuarios";
import { NOME_PAPEL } from "./tipos";

function Lateral() {
  const { usuario, sair, pode } = useAuth();
  const itens = [
    { para: "/", nome: "Painel", Ic: IcPainel, fim: true },
    { para: "/coletas", nome: "Coletas", Ic: IcColeta },
    { para: "/amostras", nome: "Amostras", Ic: IcAmostra },
    { para: "/prever", nome: "Previsão", Ic: IcPrever },
    { para: "/empresas", nome: "Empresas", Ic: IcEmpresa },
    ...(pode("admin") ? [{ para: "/usuarios", nome: "Usuários", Ic: IcUsuarios }] : []),
    { para: "/conta", nome: "Minha conta", Ic: IcConta },
  ];
  return (
    <aside className="lateral">
      <div className="marca">
        <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="8" fill="var(--primaria)" />
          <path d="M5 20c4 0 5-9 9-9s4 11 8 11 4-6 5-6" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" /></svg>
        <div>FIEP<small>Voltametria · contaminação</small></div>
      </div>
      <nav>
        {itens.map(({ para, nome, Ic, fim }) => (
          <NavLink key={para} to={para} end={fim} className={({ isActive }) => (isActive ? "ativo" : "")} title={nome}>
            <Ic /><span>{nome}</span>
          </NavLink>
        ))}
      </nav>
      <div className="rodape">
        <strong>{usuario?.nome}</strong>
        <span className="mudo">{usuario && NOME_PAPEL[usuario.papel]}</span>
        <div><button className="btn link pequeno" onClick={sair} style={{ marginTop: 6 }}><IcSair className="" /> Sair</button></div>
      </div>
    </aside>
  );
}

export default function App() {
  const { usuario, carregando, pode } = useAuth();
  const local = useLocation();
  if (carregando) return <div className="tela-login mudo">Carregando…</div>;
  if (!usuario) {
    return (
      <Routes>
        <Route path="/entrar" element={<Login />} />
        <Route path="*" element={<Navigate to="/entrar" replace state={{ de: local.pathname }} />} />
      </Routes>
    );
  }
  return (
    <div className="app">
      <Lateral />
      <main className="conteudo">
        <Routes>
          <Route path="/" element={<Painel />} />
          <Route path="/coletas" element={<Coletas />} />
          <Route path="/coletas/nova" element={pode("editar") ? <NovaColeta /> : <Navigate to="/coletas" />} />
          <Route path="/coletas/:id" element={<ColetaDetalhe />} />
          <Route path="/amostras" element={<Amostras />} />
          <Route path="/amostras/:id" element={<AmostraDetalhe />} />
          <Route path="/prever" element={<Prever />} />
          <Route path="/empresas" element={<Empresas />} />
          <Route path="/usuarios" element={pode("admin") ? <Usuarios /> : <Navigate to="/" />} />
          <Route path="/conta" element={<Conta />} />
          <Route path="/entrar" element={<Navigate to={(local.state as { de?: string })?.de || "/"} replace />} />
          <Route path="*" element={<div className="cartao">Página não encontrada.</div>} />
        </Routes>
      </main>
    </div>
  );
}
