"""Recebimento de arquivos: validação, nomes seguros e armazenamento."""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile

EXTENSOES = {".nox", ".csv", ".xlsx", ".xls", ".txt"}
MAX_ARQUIVOS = 500
MAX_BYTES = 50 * 1024 * 1024


def nome_seguro(nome: str) -> str:
    nome = re.sub(r"[^\w.\- ]+", "_", nome).strip(" .")
    return nome[:150] or "arquivo"


def caminho_relativo(caminho: str | None, nome: str) -> Path:
    """Caminho relativo informado pelo navegador (pasta da amostra/arquivo), sem '..' nem raiz."""
    partes = [nome_seguro(p) for p in PurePosixPath((caminho or nome).replace("\\", "/")).parts
              if p not in ("", ".", "..", "/")]
    if not partes:
        partes = [nome_seguro(nome)]
    return Path(*partes[-4:])


async def salvar(arquivos: list[UploadFile], destino: Path, caminhos: list[str] | None = None) -> list[Path]:
    if not arquivos:
        raise HTTPException(400, "Envie pelo menos um arquivo.")
    if len(arquivos) > MAX_ARQUIVOS:
        raise HTTPException(400, f"No máximo {MAX_ARQUIVOS} arquivos por envio.")
    caminhos = caminhos or []
    salvos = []
    for i, up in enumerate(arquivos):
        nome = Path(up.filename or "").name
        if Path(nome).suffix.lower() not in EXTENSOES:
            raise HTTPException(400, f"Tipo de arquivo não aceito: {nome}. Envie .nox, .csv ou .xlsx.")
        rel = caminho_relativo(caminhos[i] if i < len(caminhos) else None, nome)
        alvo = (destino / rel).resolve()
        if not str(alvo).startswith(str(destino.resolve())):
            raise HTTPException(400, f"Caminho inválido: {rel}")
        conteudo = await up.read()
        if len(conteudo) > MAX_BYTES:
            raise HTTPException(400, f"{nome} passa de {MAX_BYTES // 2**20} MB.")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(conteudo)
        salvos.append(alvo)
    return salvos
