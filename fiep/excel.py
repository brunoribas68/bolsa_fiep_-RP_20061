"""Converte os .nox de um lote para Excel, no mesmo formato que o NOVA exporta.

    fiep excel --entrada dados/empresa1            # gera dados/excel/empresa1/*.xlsx

Cada .nox vira um .xlsx com uma aba por medição (colunas do NOVA: Potential applied (V),
WE(1).δ.Current (A)...) e uma aba `Info` com o cabeçalho do arquivo (procedimento, canal, data).
A pipeline lê tanto o .nox quanto esse Excel (ou o exportado pelo próprio NOVA); quando os dois
existem no mesmo lote, usa o .nox. `dados/excel/` não entra no treino (seria duplicado).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from .io.nox import estilo_nova, read_nox

log = logging.getLogger(__name__)


def _aba(nome: str, usadas: set) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "_", str(nome))[:28] or "Dados"
    aba, k = base, 2
    while aba in usadas:
        aba, k = f"{base[:25]}_{k}", k + 1
    usadas.add(aba)
    return aba


def nox_para_excel(nox: Path, destino: Path) -> Path:
    res = read_nox(nox)
    destino.parent.mkdir(parents=True, exist_ok=True)
    usadas: set = set()
    with pd.ExcelWriter(destino) as w:
        tabelas = [(n, df) for n, df in res["medicoes"] if df.attrs.get("medidas")] or res["medicoes"]
        for nome, df in tabelas:
            (estilo_nova(df) if df.attrs.get("medidas") else df).to_excel(
                w, sheet_name=_aba(nome if len(tabelas) > 1 else "Dados", usadas), index=False)
        pd.DataFrame([{k: str(v) for k, v in res["info"].items()}]).to_excel(w, sheet_name="Info", index=False)
    return destino


def converter_pasta(entrada: str | Path, saida: str | Path | None = None, refazer: bool = False) -> list[Path]:
    """Converte todos os .nox de `entrada` (e subpastas) mantendo a estrutura de pastas em `saida`."""
    entrada = Path(entrada)
    if saida is None:                       # dados/empresa1 -> dados/excel/empresa1
        raiz = next((p for p in [entrada, *entrada.parents] if p.name == "dados"), entrada.parent)
        saida = raiz / "excel" / entrada.relative_to(raiz) if entrada != raiz else raiz / "excel"
    saida = Path(saida)
    gerados = []
    for nox in sorted(entrada.rglob("*.nox")):
        rel = nox.relative_to(entrada)
        if "excel" in rel.parts:
            continue
        destino = saida / rel.with_suffix(".xlsx")
        if destino.exists() and not refazer and destino.stat().st_mtime >= nox.stat().st_mtime:
            continue
        try:
            gerados.append(nox_para_excel(nox, destino))
        except Exception as e:  # noqa: BLE001
            log.warning("Não consegui converter %s: %s", nox.name, e)
    return gerados
