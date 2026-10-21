const P = (d: string) => (props: { className?: string }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true" {...props}><path d={d} /></svg>
);
export const IcPainel = P("M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-3H4zM14 7h6V4h-6z");
export const IcColeta = P("M12 3v12m0 0-4-4m4 4 4-4M4 17v3h16v-3");
export const IcAmostra = P("M9 3h6M10 3v6L5 18a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3M7.5 14h9");
export const IcPrever = P("M3 17c3 0 4-10 7-10s3 13 6 13 3-7 5-7");
export const IcEmpresa = P("M4 21V5l8-2v18M12 9l8 2v10M8 9h.01M8 13h.01M8 17h.01M16 14h.01M16 18h.01");
export const IcUsuarios = P("M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M21 19v-1a4 4 0 0 0-3-3.8M15 3.2a3.5 3.5 0 0 1 0 6.6");
export const IcConta = P("M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M4 21a8 8 0 0 1 16 0");
export const IcSair = P("M15 4h4v16h-4M10 17l5-5-5-5M15 12H3");
