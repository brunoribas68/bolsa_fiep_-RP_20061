import { useRef, useState } from "react";

export interface ArquivoComCaminho { arquivo: File; caminho: string }

const ACEITOS = /\.(nox|xlsx|xls|csv|txt)$/i;

// lê arquivos e pastas arrastados (a estrutura de pastas vira o caminho relativo)
async function lerEntrada(entrada: FileSystemEntry, prefixo: string, saida: ArquivoComCaminho[]) {
  if (entrada.isFile) {
    const f = await new Promise<File>((ok, erro) => (entrada as FileSystemFileEntry).file(ok, erro));
    if (ACEITOS.test(f.name)) saida.push({ arquivo: f, caminho: prefixo + f.name });
  } else if (entrada.isDirectory) {
    const leitor = (entrada as FileSystemDirectoryEntry).createReader();
    let lote: FileSystemEntry[];
    do {
      lote = await new Promise<FileSystemEntry[]>((ok, erro) => leitor.readEntries(ok, erro));
      for (const e of lote) await lerEntrada(e, `${prefixo}${entrada.name}/`, saida);
    } while (lote.length);
  }
}

export default function Soltar({ aoReceber, titulo, dica, pastas = true, compacto = false }: {
  aoReceber: (a: ArquivoComCaminho[]) => void; titulo: string; dica?: string; pastas?: boolean; compacto?: boolean;
}) {
  const [sobre, setSobre] = useState(false);
  const arquivos = useRef<HTMLInputElement>(null);
  const pasta = useRef<HTMLInputElement>(null);

  const deInput = (lista: FileList | null) => {
    if (!lista) return;
    aoReceber([...lista].filter(f => ACEITOS.test(f.name))
      .map(f => ({ arquivo: f, caminho: (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name })));
  };

  return (
    <div>
      <div className={`soltar${sobre ? " sobre" : ""}`} role="button" tabIndex={0}
           style={compacto ? { padding: 10 } : undefined}
           onClick={() => arquivos.current?.click()}
           onKeyDown={e => (e.key === "Enter" || e.key === " ") && arquivos.current?.click()}
           onDragOver={e => { e.preventDefault(); setSobre(true); }}
           onDragLeave={() => setSobre(false)}
           onDrop={async e => {
             e.preventDefault(); setSobre(false);
             const saida: ArquivoComCaminho[] = [];
             const itens = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry()).filter(Boolean) as FileSystemEntry[];
             for (const it of itens) await lerEntrada(it, "", saida);
             aoReceber(saida);
           }}>
        <strong>{titulo}</strong>
        {dica && <span className="pequeno">{dica}</span>}
      </div>
      <input ref={arquivos} type="file" multiple hidden accept=".nox,.xlsx,.xls,.csv,.txt"
             onChange={e => { deInput(e.target.files); e.target.value = ""; }} />
      {pastas && (
        <>
          <input ref={pasta} type="file" multiple hidden
                 {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                 onChange={e => { deInput(e.target.files); e.target.value = ""; }} />
          <div className="acoes" style={{ marginTop: 8 }}>
            <button type="button" className="btn peq" onClick={() => arquivos.current?.click()}>Escolher arquivos</button>
            <button type="button" className="btn peq" onClick={() => pasta.current?.click()}>Escolher pasta</button>
          </div>
        </>
      )}
    </div>
  );
}
