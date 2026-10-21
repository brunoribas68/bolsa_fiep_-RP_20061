"""Configuração da plataforma, toda por variáveis de ambiente.

    FIEP_DB_URL          banco (padrão: sqlite em dados/fiep.db; Postgres: postgresql+psycopg://...)
    FIEP_SECRET          chave das sessões (obrigatória em produção; sem ela, gera dados/.segredo)
    FIEP_MODELOS         pasta de modelos (padrão: modelos)
    FIEP_ARMAZENAMENTO   onde guardar os arquivos recebidos (padrão: dados/recebidos)
    FIEP_COOKIE_SEGURO   1 = cookie só por HTTPS (use em produção)
    FIEP_SESSAO_HORAS    duração da sessão (padrão: 8)
    FIEP_DADOS_EXEMPLO   1 = carregar o case de exemplo ao criar o banco (padrão: 1)
    FIEP_ADMIN_EMAIL / FIEP_ADMIN_SENHA   cria o primeiro admin se o banco não tiver usuários
    FIEP_CONFIG          configuração da pipeline (padrão: configs/default.toml)
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def _segredo() -> str:
    s = os.environ.get("FIEP_SECRET")
    if s:
        if len(s) < 32:
            raise RuntimeError("FIEP_SECRET precisa ter pelo menos 32 caracteres.")
        return s
    arq = Path(os.environ.get("FIEP_SEGREDO_ARQUIVO", "dados/.segredo"))
    if not arq.exists():
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(secrets.token_urlsafe(48))
        try:
            arq.chmod(0o600)
        except OSError:
            pass
        log.warning("FIEP_SECRET não definida: chave gerada em %s (defina FIEP_SECRET em produção).", arq)
    return arq.read_text().strip()


@dataclass
class Config:
    db_url: str | None
    segredo: str
    modelos: str
    armazenamento: Path
    cookie_seguro: bool
    sessao_horas: float
    dados_exemplo: bool
    config_pipeline: str | None

    @classmethod
    def do_ambiente(cls) -> "Config":
        cfg = os.environ.get("FIEP_CONFIG", "configs/default.toml")
        return cls(
            db_url=os.environ.get("FIEP_DB_URL") or os.environ.get("FIEP_DB"),
            segredo=_segredo(),
            modelos=os.environ.get("FIEP_MODELOS", "modelos"),
            armazenamento=Path(os.environ.get("FIEP_ARMAZENAMENTO", "dados/recebidos")),
            cookie_seguro=os.environ.get("FIEP_COOKIE_SEGURO", "0") == "1",
            sessao_horas=float(os.environ.get("FIEP_SESSAO_HORAS", "8")),
            dados_exemplo=os.environ.get("FIEP_DADOS_EXEMPLO", "1") == "1",
            config_pipeline=cfg if Path(cfg).exists() else None,
        )
