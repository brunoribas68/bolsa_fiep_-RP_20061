"""Modelo em uso: carregado uma vez e recarregado quando modelos/ATUAL muda."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import HTTPException

from fiep.modelagem import carregar


class ModeloAtual:
    def __init__(self, pasta: str):
        self.pasta = pasta
        self._pacote, self._erro, self._marca = None, None, object()

    def pacote(self) -> dict:
        atual = Path(self.pasta) / "ATUAL"
        marca = atual.read_text().strip() if atual.exists() else None
        if self._pacote is None or marca != self._marca:
            try:
                self._pacote, self._erro = carregar(self.pasta), None
            except Exception as e:  # noqa: BLE001
                self._pacote = None
                self._erro = f"Nenhum modelo treinado ainda: treine em Modelos ou com `fiep rna treinar`. ({e})"
            self._marca = marca
        if self._pacote is None:
            raise HTTPException(503, self._erro)
        return self._pacote


def limpo(v):
    """Valores numpy/pandas -> JSON."""
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (list, dict, str)) or v is None:
        return v
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def registros(df: pd.DataFrame) -> list[dict]:
    return [{k: limpo(v) for k, v in r.items()} for r in df.to_dict(orient="records")]
