export const num = (v: number | null | undefined, casas = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—"
    : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

export const pct = (v: number | null | undefined, casas = 0) =>
  v === null || v === undefined ? "—" : `${num(v * 100, casas)}%`;

export const data = (iso: string | null | undefined, hora = false) => {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return hora ? d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : d.toLocaleDateString("pt-BR");
};

export const rotulo = (v: number | null) => (v === 1 ? "Contaminada" : v === 0 ? "Não contaminada" : "Sem resultado");
