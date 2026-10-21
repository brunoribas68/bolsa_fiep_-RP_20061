from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, MetaData
from sqlalchemy.orm import DeclarativeBase

# nomes estáveis para chaves e índices: as migrations geradas ficam iguais no SQLite e no Postgres
CONVENCAO = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO)
    type_annotation_map = {dict: JSON, list: JSON}


def agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
