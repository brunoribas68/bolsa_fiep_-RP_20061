"""Modelo de dados (SQLAlchemy ORM) — a fonte da verdade do banco do projeto.

Um arquivo por domínio (cada mudança vira uma migration em `fiep/migracoes/`):

    auth.py         usuários da plataforma (login)
    cadastro.py     empresas e coletas (cada envio de arquivos)
    genossensor.py  ensaios: um voltamograma DPV por linha (branco ou RNA), com o pico e a curva
    ml.py           modelos treinados e previsões

Banco padrão: SQLite em `dados/fiep.db`; para Postgres, defina `FIEP_DB_URL`
(ex.: postgresql+psycopg://usuario:senha@host/fiep).
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .base import Base
from .auth import Usuario
from .cadastro import Coleta, Empresa
from .genossensor import Ensaio
from .ml import ModeloML, Predicao

__all__ = ["Base", "Usuario", "Empresa", "Coleta", "Ensaio", "ModeloML", "Predicao", "url_banco", "criar_engine",
           "fabrica_sessoes", "migrar"]

BANCO_PADRAO = "dados/fiep.db"


def url_banco(caminho_ou_url: str | Path | None = None) -> str:
    """Caminho de arquivo SQLite ou URL do SQLAlchemy. Sem nada: FIEP_DB_URL ou dados/fiep.db."""
    v = str(caminho_ou_url) if caminho_ou_url else os.environ.get("FIEP_DB_URL", BANCO_PADRAO)
    if "://" in v:
        return v
    Path(v).parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{Path(v).resolve().as_posix()}"


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_con, _):
    import sqlite3
    if isinstance(dbapi_con, sqlite3.Connection):
        cur = dbapi_con.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.execute("PRAGMA journal_mode = WAL")
        cur.close()


_engines: dict[str, Engine] = {}


def criar_engine(caminho_ou_url: str | Path | None = None) -> Engine:
    url = url_banco(caminho_ou_url)
    if url not in _engines:
        _engines[url] = create_engine(url, future=True)
    return _engines[url]


def migrar(caminho_ou_url: str | Path | None = None, revisao: str = "head") -> None:
    """Aplica as migrations (cria o banco se não existir)."""
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migracoes"))
    url = url_banco(caminho_ou_url)
    cfg.set_main_option("sqlalchemy.url", url)
    if url.startswith("sqlite:///"):
        arquivo = Path(url[len("sqlite:///"):])
        existentes = _tabelas_sqlite(arquivo)
        if "alembic_version" not in existentes and existentes - {"sqlite_sequence"}:
            raise RuntimeError(f"{arquivo} tem tabelas, mas não é um banco da plataforma FIEP. "
                               "Use outro caminho (--db) ou mova esse arquivo.")
        if "alembic_version" in existentes:
            conhecidas = {s.revision for s in ScriptDirectory.from_config(cfg).walk_revisions()}
            versao = _versao_sqlite(arquivo)
            if versao and versao not in conhecidas:
                raise RuntimeError(f"{arquivo} é da versão anterior da plataforma (com o case de exemplo). "
                                   "Rode `fiep db zerar`: ele guarda uma cópia, recria o banco e mantém as contas "
                                   "de usuário; depois importe os .nox de novo com `fiep rna importar`.")
    command.upgrade(cfg, revisao)


def _versao_sqlite(arquivo: Path) -> str | None:
    import sqlite3
    con = sqlite3.connect(arquivo)
    try:
        r = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return r[0] if r else None
    finally:
        con.close()


def _tabelas_sqlite(arquivo: Path) -> set[str]:
    if not arquivo.exists() or arquivo.stat().st_size == 0:
        return set()
    import sqlite3
    con = sqlite3.connect(arquivo)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        con.close()


def fabrica_sessoes(caminho_ou_url: str | Path | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=criar_engine(caminho_ou_url), expire_on_commit=False, future=True)
