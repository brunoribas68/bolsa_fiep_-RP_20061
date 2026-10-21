"""Empresas, coletas (cada envio de dados) e os arquivos recebidos."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, agora

CONJUNTOS = ("treino", "validacao", "teste")


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
    """Um envio de dados (pela plataforma ou por `fiep db importar`)."""
    __tablename__ = "coletas"
    __table_args__ = (CheckConstraint(f"conjunto IS NULL OR conjunto IN {CONJUNTOS}", name="conjunto"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True)
    descricao: Mapped[str | None] = mapped_column(String(300))
    data_coleta: Mapped[dt.date | None]
    # conjunto fixo das amostras desta coleta (None = entra no sorteio treino/validação/teste)
    conjunto: Mapped[str | None] = mapped_column(String(20))
    origem: Mapped[str | None] = mapped_column(String(300))
    versao_pipeline: Mapped[str | None] = mapped_column(String(40))
    n_medicoes: Mapped[int] = mapped_column(default=0)
    n_amostras: Mapped[int] = mapped_column(default=0)
    avisos: Mapped[list | None]
    criado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    criado_em: Mapped[dt.datetime] = mapped_column(default=agora)

    empresa: Mapped[Empresa | None] = relationship(back_populates="coletas")
    arquivos: Mapped[list["Arquivo"]] = relationship(back_populates="coleta", cascade="all, delete-orphan")


class Arquivo(Base):
    """Arquivo recebido; o SHA-256 evita importar o mesmo arquivo duas vezes."""
    __tablename__ = "arquivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    arquivo: Mapped[str] = mapped_column(String(300))
    papel: Mapped[str] = mapped_column(String(40))
    tamanho_bytes: Mapped[int | None]
    n_linhas: Mapped[int | None]
    caminho: Mapped[str | None] = mapped_column(String(500))     # onde o original ficou guardado
    coleta_id: Mapped[int | None] = mapped_column(ForeignKey("coletas.id", ondelete="CASCADE"), index=True)
    importado_em: Mapped[dt.datetime] = mapped_column(default=agora)

    coleta: Mapped[Coleta | None] = relationship(back_populates="arquivos")
