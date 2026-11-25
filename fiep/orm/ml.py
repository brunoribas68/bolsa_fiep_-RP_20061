"""Modelos treinados e previsões feitas com eles."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, agora


class ModeloML(Base):
    __tablename__ = "modelos"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    criado_em: Mapped[dt.datetime] = mapped_column(default=agora)
    algoritmo: Mapped[str] = mapped_column(String(60))
    representacao: Mapped[str] = mapped_column(String(60))
    balanced_accuracy: Mapped[float | None] = mapped_column(Float)    # a de referência (teste ou validação cruzada)
    referencia: Mapped[str | None] = mapped_column(String(40))
    n_ensaios: Mapped[int | None]
    caminho: Mapped[str | None] = mapped_column(String(500))
    cartao: Mapped[dict | None]


class Predicao(Base):
    __tablename__ = "predicoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    modelo_id: Mapped[str] = mapped_column(ForeignKey("modelos.id"), index=True)
    previsto_em: Mapped[dt.datetime] = mapped_column(default=agora)
    arquivo: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    eletrodo_id: Mapped[str | None] = mapped_column(String(60))
    resultado: Mapped[str] = mapped_column(String(30))
    prob_contaminado: Mapped[float | None] = mapped_column(Float)
    motivo: Mapped[str | None] = mapped_column(Text)
    tipo_informado: Mapped[str | None] = mapped_column(String(10))       # se o nome do arquivo diz branco/rna
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
