import { baixar } from "../api";

/** Salva um gráfico SVG como PNG (2x), com o fundo e a fonte da tela — pronto para relatório ou artigo. */
export interface Cabecalho { titulo?: string; legenda?: { nome: string; cor: string }[]; corTexto: string }

export async function svgParaPng(svg: SVGSVGElement, nome: string, fundo: string, cab?: Cabecalho,
                                 fonte = "Inter, system-ui, sans-serif") {
  const NS = "http://www.w3.org/2000/svg";
  const vb = svg.viewBox.baseVal;
  const largura = vb?.width || svg.clientWidth;
  const copia = svg.cloneNode(true) as SVGSVGElement;
  copia.querySelectorAll("[data-sem-exportar]").forEach(n => n.remove());
  // título e legenda em cima do gráfico (na tela eles ficam fora do SVG)
  let topo = 0;
  if (cab?.titulo || cab?.legenda?.length) {
    const g = document.createElementNS(NS, "g");
    const corpo = document.createElementNS(NS, "g");
    while (copia.firstChild) corpo.appendChild(copia.firstChild);
    let y = 18;
    if (cab.titulo) {
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", "8"); t.setAttribute("y", String(y)); t.setAttribute("fill", cab.corTexto);
      t.setAttribute("style", "font-size:14px;font-weight:600"); t.textContent = cab.titulo;
      g.appendChild(t); y += 22;
    }
    let x = 8;
    for (const item of cab.legenda || []) {
      const largItem = 24 + item.nome.length * 6.4;
      if (x + largItem > largura && x > 8) { x = 8; y += 18; }
      const r = document.createElementNS(NS, "rect");
      r.setAttribute("x", String(x)); r.setAttribute("y", String(y - 8)); r.setAttribute("width", "12");
      r.setAttribute("height", "4"); r.setAttribute("rx", "2"); r.setAttribute("fill", item.cor);
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", String(x + 17)); t.setAttribute("y", String(y - 2)); t.setAttribute("fill", cab.corTexto);
      t.setAttribute("style", "font-size:11px"); t.textContent = item.nome;
      g.append(r, t); x += largItem;
    }
    topo = y + 10;
    corpo.setAttribute("transform", `translate(0 ${topo})`);
    copia.append(g, corpo);
    copia.setAttribute("viewBox", `0 0 ${largura} ${(vb?.height || svg.clientHeight) + topo}`);
  }
  const altura = (vb?.height || svg.clientHeight) + topo;
  copia.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copia.setAttribute("width", String(largura));
  copia.setAttribute("height", String(altura));
  copia.setAttribute("style", `font-family: ${fonte}; overflow: visible`);
  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("x", String(vb?.x || 0)); rect.setAttribute("y", String(vb?.y || 0));
  rect.setAttribute("width", "100%"); rect.setAttribute("height", "100%"); rect.setAttribute("fill", fundo);
  copia.insertBefore(rect, copia.firstChild);
  const texto = new XMLSerializer().serializeToString(copia);
  // data: (e não blob:) porque a política de segurança da página só libera imagens 'self' e data:
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(texto)}`;
  {
    const img = new Image();
    await new Promise<void>((ok, erro) => { img.onload = () => ok(); img.onerror = () => erro(new Error("Não foi possível gerar a imagem.")); img.src = url; });
    const escala = 2, canvas = document.createElement("canvas");
    canvas.width = largura * escala; canvas.height = altura * escala;
    const ctx = canvas.getContext("2d")!;
    ctx.scale(escala, escala);
    ctx.drawImage(img, 0, 0, largura, altura);
    const png = await new Promise<Blob | null>(ok => canvas.toBlob(ok, "image/png"));
    if (png) baixar(png, nome.endsWith(".png") ? nome : `${nome}.png`);
  }
}

/** Tabela para CSV (separador ";" e vírgula decimal abrem direto no Excel em português). */
export function csv(linhas: Record<string, unknown>[], colunas: { id: string; nome: string }[], nome: string) {
  const cel = (v: unknown) => {
    if (v === null || v === undefined) return "";
    if (typeof v === "number") return String(v).replace(".", ",");
    const s = String(v);
    return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const texto = [colunas.map(c => cel(c.nome)).join(";"), ...linhas.map(l => colunas.map(c => cel(l[c.id])).join(";"))].join("\r\n");
  baixar(new Blob(["﻿" + texto], { type: "text/csv;charset=utf-8" }), nome);
}
