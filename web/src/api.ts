// Cliente da API: mesmo domínio, cookie de sessão httpOnly e o cabeçalho de proteção CSRF.
export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

let aoExpirar: (() => void) | null = null;
export const quandoSessaoExpirar = (fn: () => void) => { aoExpirar = fn; };

async function pedir<T>(metodo: string, url: string, corpo?: unknown): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "fiep" };
  let body: BodyInit | undefined;
  if (corpo instanceof FormData) body = corpo;
  else if (corpo !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(corpo); }
  const r = await fetch(url, { method: metodo, headers, body, credentials: "same-origin" });
  if (r.status === 401 && !url.endsWith("/auth/login") && !url.endsWith("/auth/eu")) aoExpirar?.();
  if (!r.ok) {
    let detalhe = `Erro ${r.status}`;
    try {
      const j = await r.json();
      detalhe = typeof j.detail === "string" ? j.detail
        : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join("; ") : detalhe;
    } catch { /* resposta sem JSON */ }
    throw new ErroApi(r.status, detalhe);
  }
  const tipo = r.headers.get("content-type") || "";
  return (tipo.includes("application/json") ? r.json() : r.blob()) as Promise<T>;
}

export const api = {
  get: <T,>(url: string) => pedir<T>("GET", url),
  post: <T,>(url: string, corpo?: unknown) => pedir<T>("POST", url, corpo),
  patch: <T,>(url: string, corpo: unknown) => pedir<T>("PATCH", url, corpo),
  del: <T,>(url: string) => pedir<T>("DELETE", url),
};

export function baixar(blob: Blob, nome: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nome;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
