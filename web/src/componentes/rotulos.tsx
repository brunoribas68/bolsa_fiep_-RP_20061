import { pct } from "../formato";

export function ChipResultado({ r }: { r: string | null | undefined }) {
  if (!r) return <span className="mudo">—</span>;
  const c = r === "CONTAMINADA" ? "c1" : r === "NÃO CONTAMINADA" ? "c0" : r === "REPETIR MEDIÇÃO" ? "rep" : "sem";
  const txt = r.charAt(0) + r.slice(1).toLowerCase();
  return <span className={`chip ${c}`}>{txt}</span>;
}

export function ChipRotulo({ v }: { v: number | null }) {
  if (v === 1) return <span className="chip c1">Contaminada</span>;
  if (v === 0) return <span className="chip c0">Não contaminada</span>;
  return <span className="chip sem">Sem resultado</span>;
}

export function SeloQC({ v }: { v: string | null }) {
  if (!v) return <span className="selo">—</span>;
  return <span className={`selo ${v.toLowerCase()}`}>{v}</span>;
}

export function BarraProb({ p, limiar }: { p: number | null; limiar: number }) {
  if (p === null || p === undefined) return <span className="mudo">—</span>;
  return (
    <div className="prob" title={`Probabilidade ${pct(p, 1)} · limiar ${pct(limiar)}`}>
      <div className="trilho"><i style={{ width: `${p * 100}%` }} /><b style={{ left: `${limiar * 100}%` }} /></div>
      <span className="mono">{pct(p)}</span>
    </div>
  );
}
