"""Empresas e coletas (cada envio de arquivos)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, agora


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), unique=True)
    cidade: Mapped[str | None] = mapped_column(String(120))
    segmento: Mapped[str | None] = mapped_column(String(120))
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[dt.datetime] = mapped_column(default=agora)

    coletas: Mapped[list["Coleta"]] = relationship(back_populates="empresa")


class Coleta(Base):
    """Um envio de .nox (pela plataforma ou por `fiep rna importar`)."""
    __tablename__ = "coletas"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True)
    descricao: Mapped[str | None] = mapped_column(String(300))
    data_coleta: Mapped[dt.date | None]
    origem: Mapped[str | None] = mapped_column(String(300))
    n_ensaios: Mapped[int] = mapped_column(default=0)
    avisos: Mapped[list | None]
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[dt.datetime] = mapped_column(default=agora)

    empresa: Mapped[Empresa | None] = relationship(back_populates="coletas")
