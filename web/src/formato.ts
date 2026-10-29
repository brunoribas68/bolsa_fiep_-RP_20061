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

export const rotulo = (v: number | null) => (v === 1 ? "Contaminada" : v === 0 ? "Não contaminada" : "Sem resultado");
