"""Banco de dados do projeto, sobre o modelo ORM (`fiep/orm/`) e as migrations (`fiep/migracoes/`).

    s = conectar("dados/fiep.db")        # aplica as migrations e abre uma sessão (SQLite ou FIEP_DB_URL)
    sql(s, "SELECT ...")                 # consulta livre -> DataFrame
    zerar("dados/fiep.db")               # apaga tudo (com cópia de segurança) e mantém os usuários

Os ensaios entram por `fiep.genossensor.importar`; modelos e previsões por `fiep.modelagem`.
"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from .orm import fabrica_sessoes, migrar

# tabelas da versão com o case de exemplo (só para o `zerar` limpar um Postgres antigo)
TABELAS_ANTIGAS = ("plaqueamentos", "qc", "curvas", "medicoes", "amostras", "arquivos")


def conectar(caminho: str | Path | None = None) -> Session:
    """Aplica as migrations pendentes e devolve uma sessão. Sem caminho: FIEP_DB_URL ou dados/fiep.db."""
    migrar(caminho)
    return fabrica_sessoes(caminho)()


def sql(s: Session, consulta: str, params: tuple | dict = ()) -> pd.DataFrame:
    """Consulta SQL livre. Parâmetros com `?` no SQLite."""
    res = s.connection().exec_driver_sql(consulta, params) if params else s.connection().exec_driver_sql(consulta)
    return pd.DataFrame(res.fetchall(), columns=list(res.keys()))


def _valor(coluna, v):
    """Valor lido com SELECT * (texto no SQLite) de volta ao tipo da coluna."""
    if isinstance(v, str) and coluna.type.python_type in (dt.datetime, dt.date):
        return dt.datetime.fromisoformat(v)
    return v


def zerar(caminho: str | Path | None = None, manter_usuarios: bool = True) -> dict:
    """Apaga TODOS os dados do banco e recria vazio pelas migrations. As contas de usuário são mantidas,
    salvo `manter_usuarios=False`. Serve também para sair de um banco da versão anterior.

    SQLite: antes guarda uma cópia do arquivo em dados/backup/. Postgres: apaga as tabelas.
    Não mexe em modelos/ (treine de novo para trocar o modelo em uso)."""
    from sqlalchemy import inspect, text
    from .orm import Base, Usuario, _engines, criar_engine, url_banco
    url = url_banco(caminho)
    eng = criar_engine(url)
    usuarios_salvos: list[dict] = []
    if manter_usuarios and "usuarios" in inspect(eng).get_table_names():
        with eng.connect() as c:
            # SELECT * e não o modelo atual: o banco pode ser de uma versão com outras colunas
            usuarios_salvos = [dict(r._mapping) for r in c.execute(text("SELECT * FROM usuarios"))]
    backup = None
    if url.startswith("sqlite:///"):
        arquivo = Path(url[len("sqlite:///"):])
        _engines.pop(url, eng).dispose()                 # solta o arquivo (Windows)
        if arquivo.exists():
            pasta = arquivo.parent / "backup"
            pasta.mkdir(parents=True, exist_ok=True)
            backup = pasta / f"{arquivo.stem}_{dt.datetime.now():%Y%m%d-%H%M%S}{arquivo.suffix}"
            shutil.copy2(arquivo, backup)
            for extra in ("", "-wal", "-shm"):
                f = arquivo.with_name(arquivo.name + extra)
                if f.exists():
                    try:
                        f.unlink()
                    except PermissionError as e:       # Windows: o arquivo está aberto (fiep servir rodando)
                        raise RuntimeError(f"{arquivo} está em uso (o fiep servir está rodando?). Pare a plataforma "
                                           "(Ctrl+C no terminal dela) e rode o fiep db zerar de novo. "
                                           "Nada foi apagado.") from e
    else:
        with eng.begin() as c:
            for t in TABELAS_ANTIGAS:
                c.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
            Base.metadata.drop_all(c)
            c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    migrar(url)
    if usuarios_salvos:
        colunas = {c.name for c in Usuario.__table__.columns}
        with criar_engine(url).begin() as c:
            c.execute(Usuario.__table__.insert(), [{k: _valor(Usuario.__table__.c[k], v) for k, v in u.items()
                                                    if k in colunas} for u in usuarios_salvos])
    return {"backup": str(backup) if backup else None, "usuarios_mantidos": len(usuarios_salvos),
            "emails": [u["email"] for u in usuarios_salvos]}
