"""Modelo em uso: carregado uma vez e recarregado quando modelos/ATUAL muda."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import HTTPException

from fiep.config import load_config
from fiep.model import carregar


class ModeloAtual:
    def __init__(self, pasta: str, config_pipeline: str | None):
        self.pasta, self.config_pipeline = pasta, config_pipeline
        self._pacote, self._erro, self._marca = None, None, object()

    def pacote(self) -> dict:
        atual = Path(self.pasta) / "ATUAL"
        marca = atual.read_text().strip() if atual.exists() else None
        if self._pacote is None or marca != self._marca:
            try:
                self._pacote, self._erro = carregar(self.pasta), None
            except Exception as e:  # noqa: BLE001
                self._pacote = None
                self._erro = f"Nenhum modelo treinado em '{self.pasta}': rode `fiep experimento`. ({e})"
            self._marca = marca
        if self._pacote is None:
            raise HTTPException(503, self._erro)
        return self._pacote

    def niveis(self) -> dict | None:
        return load_config(self.config_pipeline).get("niveis")


def limpo(v):
    """Valores numpy/pandas -> JSON."""
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (list, dict, str)) or v is None:
        return v
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def registros(df: pd.DataFrame) -> list[dict]:
    return [{k: limpo(v) for k, v in r.items()} for r in df.to_dict(orient="records")]
