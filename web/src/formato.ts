export const num = (v: number | null | undefined, casas = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—"
    : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

export const pct = (v: number | null | undefined, casas = 0) =>
  v === null || v === undefined ? "—" : `${num(v * 100, casas)}%`;

export const data = (iso: string | null | undefined, hora = false) => {
  if (!iso) return "—";
  // com fuso ("Z", "+00:00", "-03:00") usa o fuso dado; sem fuso, o servidor grava em UTC
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : /([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return hora ? d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : d.toLocaleDateString("pt-BR");
};

/** Cor de uma curva: branco em cinza; RNA numa escala de uma cor só, mais escura quanto maior a concentração. */
export function corEnsaio(tipo: string, conc: number, concs: number[], escuro: boolean) {
  if (tipo !== "rna") return escuro ? "#c9c6bd" : "#3f3d38";
  const pos = concs.filter(c => c > 0);
  const lo = Math.log10(Math.min(...pos)), hi = Math.log10(Math.max(...pos));
  const f = hi > lo ? (Math.log10(conc) - lo) / (hi - lo) : 1;
  const [a, b] = escuro ? [[255, 196, 160], [235, 104, 52]] : [[245, 170, 120], [176, 52, 12]];
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
}

export const concTexto = (c: number) => `${num(c, c < 1 ? 2 : 1)} ng/mL`;
