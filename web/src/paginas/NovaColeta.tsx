import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Soltar, { type ArquivoComCaminho } from "../componentes/Soltar";
import type { Coleta, Empresa } from "../tipos";
import { useCarregar } from "../usar";

interface AmostraForm { chave: number; codigo: string; rotulo: "" | "0" | "1"; carga: string; arquivos: ArquivoComCaminho[] }

let seq = 1;
const nova = (codigo = "", arquivos: ArquivoComCaminho[] = [], rotulo: AmostraForm["rotulo"] = ""): AmostraForm =>
  ({ chave: seq++, codigo, rotulo, carga: "", arquivos });
const CODIGO_OK = /^[\w.\-]{1,80}$/;

function rotuloDoCaminho(caminho: string): AmostraForm["rotulo"] {
  const c = caminho.toLowerCase();
  if (/n[aã]o[_\- ]?contaminad|negativ|control[e]?[_\- ]?neg/.test(c)) return "0";
  if (/contaminad|positiv/.test(c)) return "1";
  return "";
}

export default function NovaColeta() {
  const navegar = useNavigate();
  const { dados: empresas, recarregar } = useCarregar<Empresa[]>("/api/empresas");
  const [empresaId, setEmpresaId] = useState("");
  const [novaEmpresa, setNovaEmpresa] = useState("");
  const [dataColeta, setDataColeta] = useState(new Date().toISOString().slice(0, 10));
  const [descricao, setDescricao] = useState("");
  const [conjunto, setConjunto] = useState("");
  const [amostras, setAmostras] = useState<AmostraForm[]>([]);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  // pasta do lote: cada subpasta é uma amostra (o nome da pasta vira o código)
  function receberLote(lista: ArquivoComCaminho[]) {
    const grupos = new Map<string, ArquivoComCaminho[]>();
    for (const a of lista) {
      const partes = a.caminho.split("/");
      const chave = partes.length >= 2 ? partes.slice(0, -1).join("/") : "";
      grupos.set(chave, [...(grupos.get(chave) || []), a]);
    }
    const novas = [...grupos.entries()].map(([pasta, arqs]) =>
      nova(pasta ? pasta.split("/").pop()! : "", arqs, rotuloDoCaminho(pasta)));
    setAmostras(atual => [...atual.filter(a => a.arquivos.length || a.codigo), ...novas]);
  }

  const alterar = (chave: number, mud: Partial<AmostraForm>) =>
    setAmostras(lista => lista.map(a => (a.chave === chave ? { ...a, ...mud } : a)));

  const problemas = (() => {
    const p: string[] = [];
    if (!amostras.length) p.push("Adicione pelo menos uma amostra com arquivos.");
    const codigos = amostras.map(a => a.codigo.trim());
    amostras.forEach((a, i) => {
      if (!a.codigo.trim()) p.push(`Amostra ${i + 1}: informe o código.`);
      else if (!CODIGO_OK.test(a.codigo.trim())) p.push(`Amostra ${a.codigo}: use só letras, números, ponto, hífen e _.`);
      if (!a.arquivos.length) p.push(`Amostra ${a.codigo || i + 1}: sem arquivos.`);
      if (a.carga && Number.isNaN(Number(a.carga.replace(",", ".")))) p.push(`Amostra ${a.codigo}: carga inválida.`);
    });
    const rep = codigos.filter((c, i) => c && codigos.indexOf(c) !== i);
    if (rep.length) p.push(`Códigos repetidos: ${[...new Set(rep)].join(", ")}.`);
    return p;
  })();

  async function enviar() {
    setErro("");
    setEnviando(true);
    try {
      let eid = empresaId;
      if (empresaId === "nova") {
        const e = await api.post<Empresa>("/api/empresas", { nome: novaEmpresa });
        eid = String(e.id);
        recarregar();
      }
      const fd = new FormData();
      for (const a of amostras) {
        for (const f of a.arquivos) {
          fd.append("arquivos", f.arquivo, f.arquivo.name);
          fd.append("caminhos", `${a.codigo.trim()}/${f.arquivo.name}`);
        }
      }
      if (eid) fd.append("empresa_id", eid);
      if (descricao) fd.append("descricao", descricao);
      if (dataColeta) fd.append("data_coleta", dataColeta);
      if (conjunto) fd.append("conjunto", conjunto);
      fd.append("amostras", JSON.stringify(amostras.map(a => ({
        sample_id: a.codigo.trim(),
        contamination_status: a.rotulo === "" ? null : Number(a.rotulo),
        sample_log10_mean_cfu_ml: a.carga ? Number(a.carga.replace(",", ".")) : null,
      }))));
      const c = await api.post<Coleta>("/api/coletas", fd);
      navegar(`/coletas/${c.id}`, { state: { criada: true } });
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  const total = amostras.reduce((n, a) => n + a.arquivos.length, 0);
  return (
    <>
      <div className="cabecalho"><div><h1>Nova coleta</h1>
        <p>Envie os voltamogramas (.nox ou Excel/CSV exportado pelo NOVA) de cada amostra e o resultado do plaqueamento.</p></div></div>
      <div className="pilha">
        <section className="cartao">
          <h2>1 · Dados da coleta</h2>
          <div className="linha-campos">
            <label className="campo">Empresa
              <select value={empresaId} onChange={e => setEmpresaId(e.target.value)}>
                <option value="">— sem empresa —</option>
                {empresas?.map(e => <option key={e.id} value={e.id}>{e.nome}</option>)}
                <option value="nova">+ Cadastrar nova empresa…</option>
              </select>
            </label>
            {empresaId === "nova" && (
              <label className="campo">Nome da nova empresa
                <input value={novaEmpresa} onChange={e => setNovaEmpresa(e.target.value)} maxLength={160} />
              </label>
            )}
            <label className="campo">Data da coleta
              <input type="date" value={dataColeta} onChange={e => setDataColeta(e.target.value)} />
            </label>
            <label className="campo">Descrição
              <input value={descricao} onChange={e => setDescricao(e.target.value)} maxLength={300} placeholder="ex.: visita 2 — linha de envase" />
            </label>
            <label className="campo">Uso no treino
              <select value={conjunto} onChange={e => setConjunto(e.target.value)}>
                <option value="">Sorteio (50% treino · 25% validação · 25% teste)</option>
                <option value="treino">Sempre no treino</option>
                <option value="validacao">Sempre na validação</option>
                <option value="teste">Reservar para teste (validação externa)</option>
              </select>
            </label>
          </div>
        </section>

        <section className="cartao">
          <h2>2 · Amostras e arquivos</h2>
          <p className="mudo pequeno" style={{ marginTop: -6 }}>
            Cada eletrodo precisa das três etapas do sensor (ex.: bloqueio → mAb-NS1 → final, ou carbono → sonda → rRNA).
            Etapa e eletrodo são lidos dos nomes dos arquivos (ex.: <span className="mono">final-E3.nox</span>).
          </p>
          <Soltar aoReceber={receberLote} titulo="Arraste a pasta do lote aqui"
                  dica="Uma subpasta por amostra — o nome da pasta vira o código (pastas contaminada/ e nao_contaminada/ já preenchem o resultado)." />
          <div style={{ marginTop: 16 }}>
            {amostras.map((a, i) => (
              <div className="amostra-cartao" key={a.chave}>
                <div className="topo">
                  <label className="campo">Código da amostra
                    <input value={a.codigo} onChange={e => alterar(a.chave, { codigo: e.target.value })} placeholder={`ex.: EMP1-${String(i + 1).padStart(3, "0")}`} />
                  </label>
                  <label className="campo">Resultado do plaqueamento
                    <select value={a.rotulo} onChange={e => alterar(a.chave, { rotulo: e.target.value as AmostraForm["rotulo"] })}>
                      <option value="">Ainda sem resultado</option>
                      <option value="1">Contaminada</option>
                      <option value="0">Não contaminada</option>
                    </select>
                  </label>
                  <label className="campo">Carga <small>log₁₀ UFC/mL</small>
                    <input inputMode="decimal" value={a.carga} onChange={e => alterar(a.chave, { carga: e.target.value })} placeholder="opcional" />
                  </label>
                  <button type="button" className="btn perigo peq" onClick={() => setAmostras(l => l.filter(x => x.chave !== a.chave))}>Remover</button>
                </div>
                <Soltar compacto pastas={false} titulo="Adicionar arquivos desta amostra"
                        aoReceber={l => alterar(a.chave, { arquivos: [...a.arquivos, ...l] })} />
                <div className="arquivos">
                  {a.arquivos.map((f, j) => (
                    <span className="arquivo" key={j}>{f.arquivo.name}
                      <button type="button" aria-label={`remover ${f.arquivo.name}`}
                              onClick={() => alterar(a.chave, { arquivos: a.arquivos.filter((_, k) => k !== j) })}>×</button>
                    </span>))}
                </div>
              </div>
            ))}
          </div>
          <div className="acoes" style={{ marginTop: 12 }}>
            <button type="button" className="btn" onClick={() => setAmostras(l => [...l, nova()])}>+ Adicionar amostra</button>
            <span className="mudo pequeno">{amostras.length} amostra(s) · {total} arquivo(s)</span>
          </div>
        </section>

        <section className="cartao">
          <h2>3 · Enviar</h2>
          {problemas.length > 0 && amostras.length > 0 && (
            <div className="aviso"><strong>Antes de enviar:</strong><ul>{problemas.map(p => <li key={p}>{p}</li>)}</ul></div>
          )}
          {erro && <div className="erro" role="alert" style={{ marginTop: 10 }}>{erro}</div>}
          <div className="acoes" style={{ marginTop: 12 }}>
            <button className="btn prim" disabled={enviando || problemas.length > 0 || (empresaId === "nova" && !novaEmpresa.trim())}
                    onClick={enviar}>{enviando ? "Enviando e processando…" : "Enviar coleta"}</button>
            <span className="mudo pequeno">Os arquivos são guardados, lidos, passam pelo controle de qualidade e vão para o banco.</span>
          </div>
        </section>
      </div>
    </>
  );
}
