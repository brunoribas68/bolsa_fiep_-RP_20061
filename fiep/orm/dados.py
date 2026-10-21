"""Amostras, referência microbiológica, medições (voltamogramas) e controle de qualidade.

Os nomes de coluna de `amostras` e `medicoes` são os mesmos da pipeline (sample_id,
sensor_state...), para que `fiep.db.carregar` devolva um Dataset sem traduções.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, agora
from .cadastro import CONJUNTOS


class Amostra(Base):
    __tablename__ = "amostras"
    __table_args__ = (
        CheckConstraint("contamination_status IS NULL OR contamination_status IN (0, 1)", name="rotulo"),
        CheckConstraint(f"conjunto IS NULL OR conjunto IN {CONJUNTOS}", name="conjunto"),
    )

    sample_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True)
    coleta_id: Mapped[int | None] = mapped_column(ForeignKey("coletas.id", ondelete="SET NULL"), index=True)
    target_bacterium: Mapped[str | None] = mapped_column(String(120))
    # rótulo do plaqueamento: 1 contaminada, 0 não contaminada, NULL ainda sem resultado
    contamination_status: Mapped[int | None]
    sample_log10_mean_cfu_ml: Mapped[float | None] = mapped_column(Float)
    surface_type: Mapped[str | None] = mapped_column(String(120))
    sensor_lot: Mapped[str | None] = mapped_column(String(60))
    conjunto: Mapped[str | None] = mapped_column(String(20))
    observacoes: Mapped[str | None] = mapped_column(Text)
    extras: Mapped[dict | None]
    atualizado_em: Mapped[dt.datetime] = mapped_column(default=agora, onupdate=agora)
    atualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    medicoes: Mapped[list["Medicao"]] = relationship(back_populates="amostra", passive_deletes=True)
    plaqueamentos: Mapped[list["Plaqueamento"]] = relationship(back_populates="amostra",
                                                               cascade="all, delete-orphan")


class Plaqueamento(Base):
    __tablename__ = "plaqueamentos"

    sample_id: Mapped[str] = mapped_column(ForeignKey("amostras.sample_id", ondelete="CASCADE"), primary_key=True)
    plating_replicate_id: Mapped[int] = mapped_column(primary_key=True)
    colony_count: Mapped[float | None] = mapped_column(Float)
    dilution_exponent: Mapped[float | None] = mapped_column(Float)
    plated_volume_ml: Mapped[float | None] = mapped_column(Float)
    plating_qualifier: Mapped[str | None] = mapped_column(String(40))
    calculated_cfu_ml: Mapped[float | None] = mapped_column(Float)
    log10_cfu_ml: Mapped[float | None] = mapped_column(Float)
    arquivo_origem: Mapped[str | None] = mapped_column(String(300))
    extras: Mapped[dict | None]

    amostra: Mapped[Amostra] = relationship(back_populates="plaqueamentos")


class Medicao(Base):
    """Um voltamograma: amostra, réplica (eletrodo), estágio do sensor e técnica."""
    __tablename__ = "medicoes"
    __table_args__ = (Index("ix_medicoes_amostra_replica", "sample_id", "replicate_id"),)

    measurement_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    sample_id: Mapped[str | None] = mapped_column(ForeignKey("amostras.sample_id", ondelete="CASCADE"))
    replicate_id: Mapped[str | None] = mapped_column(String(40))
    sensor_state: Mapped[str | None] = mapped_column(String(60))
    tecnica: Mapped[str | None] = mapped_column(String(20))
    fonte: Mapped[str | None] = mapped_column(String(20))
    arquivo_origem: Mapped[str | None] = mapped_column(String(300))
    contamination_status: Mapped[int | None]
    qc_flag: Mapped[str | None] = mapped_column(String(20))      # marcação manual (planilha/plataforma)
    sensor_id: Mapped[str | None] = mapped_column(String(60))
    sensor_lot: Mapped[str | None] = mapped_column(String(60))
    experimental_batch: Mapped[str | None] = mapped_column(String(60))
    surface_type: Mapped[str | None] = mapped_column(String(120))
    operator_id: Mapped[str | None] = mapped_column(String(60))
    measurement_date: Mapped[str | None] = mapped_column(String(30))
    extras: Mapped[dict | None]
    coleta_id: Mapped[int | None] = mapped_column(ForeignKey("coletas.id", ondelete="SET NULL"), index=True)

    amostra: Mapped[Amostra | None] = relationship(back_populates="medicoes")
    curva: Mapped["Curva | None"] = relationship(back_populates="medicao", cascade="all, delete-orphan",
                                                uselist=False)


class Curva(Base):
    """Os pontos do voltamograma, guardados como vetores (uma linha por medição)."""
    __tablename__ = "curvas"

    measurement_id: Mapped[str] = mapped_column(ForeignKey("medicoes.measurement_id", ondelete="CASCADE"),
                                                primary_key=True)
    n_pontos: Mapped[int]
    potential_v: Mapped[list]
    current_ua: Mapped[list]
    scan_index: Mapped[list | None]
    e_medido_v: Mapped[list | None]          # só .nox: potencial medido (controle de qualidade)
    i_bruta_ua: Mapped[list | None]          # só .nox: corrente de base/forward (sobrecarga)

    medicao: Mapped[Medicao] = relationship(back_populates="curva")


class ResultadoQC(Base):
    __tablename__ = "qc"

    measurement_id: Mapped[str] = mapped_column(ForeignKey("medicoes.measurement_id", ondelete="CASCADE"),
                                                primary_key=True)
    versao_pipeline: Mapped[str] = mapped_column(String(40), primary_key=True)
    avaliado_em: Mapped[dt.datetime] = mapped_column(default=agora)
    qc_auto: Mapped[str | None] = mapped_column(String(20))
    qc_planilha: Mapped[str | None] = mapped_column(String(20))
    qc_final: Mapped[str | None] = mapped_column(String(20))
    qc_motivos: Mapped[str | None] = mapped_column(Text)
    i_max_ua: Mapped[float | None] = mapped_column(Float)
