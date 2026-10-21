"""Ambiente do Alembic. A URL vem de `fiep.orm.migrar()`, de `-x url=...` ou de FIEP_DB_URL."""
from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from fiep.orm import Base, url_banco

config = context.config
url = context.get_x_argument(as_dictionary=True).get("url") or config.get_main_option("sqlalchemy.url") \
    or url_banco()
config.set_main_option("sqlalchemy.url", url_banco(url))
alvo = Base.metadata


def _sem_views(obj, nome, tipo, refletido, comparado):
    # views (v_*) são criadas por SQL nas migrations; o autogenerate não deve tentar apagá-las
    return not (tipo == "table" and str(nome).startswith("v_"))


def offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=alvo, literal_binds=True,
                      render_as_batch=True, include_object=_sem_views)
    with context.begin_transaction():
        context.run_migrations()


def online():
    eng = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                             poolclass=pool.NullPool)
    with eng.connect() as con:
        # render_as_batch: ALTER TABLE no SQLite (recria a tabela por baixo dos panos)
        context.configure(connection=con, target_metadata=alvo, render_as_batch=True, include_object=_sem_views,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


offline() if context.is_offline_mode() else online()
