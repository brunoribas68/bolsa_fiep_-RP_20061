"""Modelos treinados e previsões feitas com eles."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, agora


class ModeloML(Base):
    __tablename__ = "modelos"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    criado_em: Mapped[str | None] = mapped_column(String(40))
    algoritmo: Mapped[str | None] = mapped_column(String(160))
    versao_pipeline: Mapped[str | None] = mapped_column(String(40))
    commit_codigo: Mapped[str | None] = mapped_column(String(60))
    limiar: Mapped[float | None] = mapped_column(Float)
    balanced_accuracy: Mapped[float | None] = mapped_column(Float)
    sensibilidade: Mapped[float | None] = mapped_column(Float)
    especificidade: Mapped[float | None] = mapped_column(Float)
    roc_auc: Mapped[float | None] = mapped_column(Float)
    n_amostras: Mapped[int | None]
    impressao_dados: Mapped[str | None] = mapped_column(String(40))
    caminho: Mapped[str | None] = mapped_column(String(500))
    cartao: Mapped[dict | None]


class Predicao(Base):
    __tablename__ = "predicoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    modelo_id: Mapped[str] = mapped_column(ForeignKey("modelos.id"), index=True)
    previsto_em: Mapped[dt.datetime] = mapped_column(default=agora)
    sample_id: Mapped[str | None] = mapped_column(String(120), index=True)
    replicate_id: Mapped[str | None] = mapped_column(String(40))
    measurement_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(60))
    resultado: Mapped[str | None] = mapped_column(String(30))
    prob_contaminada: Mapped[float | None] = mapped_column(Float)
    confianca: Mapped[float | None] = mapped_column(Float)
    log10_ufc_ml_estimado: Mapped[float | None] = mapped_column(Float)
    nivel_contaminacao: Mapped[str | None] = mapped_column(String(40))
    motivo: Mapped[str | None] = mapped_column(Text)
    rotulo_informado: Mapped[int | None]
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
