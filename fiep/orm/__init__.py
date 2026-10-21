"""Modelo de dados (SQLAlchemy ORM) — a fonte da verdade do banco do projeto.

As tabelas ficam separadas por domínio, um arquivo cada, para que possam mudar à vontade até o fim
do projeto (cada mudança vira uma migration em `fiep/migracoes/`):

    auth.py      usuários da plataforma (login)
    cadastro.py  empresas e coletas (cada envio de dados), arquivos recebidos
    dados.py     amostras, plaqueamentos, medições, curvas, controle de qualidade
    ml.py        modelos treinados e previsões

O mesmo modelo serve a pipeline (`fiep.db`), a API (`api/`) e as migrations (Alembic).
Banco padrão: SQLite em `dados/fiep.db`; para Postgres, defina `FIEP_DB_URL`
(ex.: postgresql+psycopg://usuario:senha@host/fiep).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .base import Base
from .auth import Usuario
from .cadastro import Arquivo, Coleta, Empresa
from .dados import Amostra, Curva, Medicao, Plaqueamento, ResultadoQC
from .ml import ModeloML, Predicao

__all__ = ["Base", "Usuario", "Empresa", "Coleta", "Arquivo", "Amostra", "Plaqueamento", "Medicao", "Curva",
           "ResultadoQC", "ModeloML", "Predicao", "url_banco", "criar_engine", "fabrica_sessoes", "migrar"]

BANCO_PADRAO = "dados/fiep.db"
log = logging.getLogger(__name__)


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


def migrar(caminho_ou_url: str | Path | None = None, dados_exemplo: bool = True, revisao: str = "head") -> None:
    """Aplica as migrations (cria o banco se não existir). `dados_exemplo=False` pula a carga do case."""
    from alembic import command
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migracoes"))
    cfg.set_main_option("sqlalchemy.url", url_banco(caminho_ou_url))
    url = url_banco(caminho_ou_url)
    antigo = None
    if url.startswith("sqlite:///"):
        from .. import legado
        arquivo = Path(url[len("sqlite:///"):])
        if legado.eh_antigo(arquivo):
            # banco da versão anterior (sem migrations): guarda uma cópia e converte
            if url in _engines:
                _engines.pop(url).dispose()          # solta o arquivo (no Windows não renomeia aberto)
            antigo = legado.nome_backup(arquivo)
            arquivo.replace(antigo)
            for extra in ("-wal", "-shm"):
                f = arquivo.with_name(arquivo.name + extra)
                if f.exists():
                    f.replace(antigo.with_name(antigo.name + extra))
            dados_exemplo = False                    # o banco já tinha dados: não mistura o exemplo
            log.warning("Banco antigo encontrado: cópia em %s; convertendo para o formato novo.", antigo)
        elif "alembic_version" not in legado.tabelas(arquivo) and legado.tabelas(arquivo) - {"sqlite_sequence"}:
            raise RuntimeError(f"{arquivo} tem tabelas, mas não é um banco da plataforma FIEP. "
                               "Use outro caminho (--db) ou mova esse arquivo.")
    cfg.attributes["dados_exemplo"] = dados_exemplo
    command.upgrade(cfg, revisao)
    if antigo is not None:
        from .. import legado
        s = fabrica_sessoes(caminho_ou_url)()
        try:
            r = legado.converter(antigo, s)
        finally:
            s.close()
        log.warning("Conversão concluída: %s medições, %s modelos, %s previsões. O arquivo antigo ficou em %s.",
                    r["medicoes"], r["modelos"], r["previsoes"], antigo)


def fabrica_sessoes(caminho_ou_url: str | Path | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=criar_engine(caminho_ou_url), expire_on_commit=False, future=True)
