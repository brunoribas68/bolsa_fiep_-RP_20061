"""Ensaios do genossensor: uma linha por voltamograma DPV, branco ou com RNA, com o pico já medido.

Dicionário completo: docs/DICIONARIO_DADOS.md.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, agora

# branco: eletrodo só com o elemento de captura (não contaminado); rna: com o RNA da bactéria (contaminado)
TIPOS = ("branco", "rna")
QC = ("PASS", "FAIL")


class Ensaio(Base):
    __tablename__ = "ensaios"
    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS}", name="tipo"),
        CheckConstraint("concentracao >= 0", name="concentracao"),
        CheckConstraint("tipo = 'rna' OR concentracao = 0", name="branco_sem_rna"),
        CheckConstraint(f"qc_flag IS NULL OR qc_flag IN {QC}", name="qc_flag"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True)
    coleta_id: Mapped[int | None] = mapped_column(ForeignKey("coletas.id", ondelete="CASCADE"), index=True)
    # identificação
    eletrodo_id: Mapped[str] = mapped_column(String(60), index=True)
    canal: Mapped[str | None] = mapped_column(String(60))
    # o que está no eletrodo
    elemento_captura: Mapped[str | None] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(10))
    bacteria: Mapped[str | None] = mapped_column(String(120))
    concentracao: Mapped[float] = mapped_column(Float, default=0.0)        # ng/mL
    branco_id: Mapped[int | None] = mapped_column(ForeignKey("ensaios.id", ondelete="SET NULL"))
    # medição
    tecnica: Mapped[str] = mapped_column(String(20), default="DPV")
    tipo_eletrodo: Mapped[str | None] = mapped_column(String(60))
    tratamento: Mapped[str | None] = mapped_column(String(60))
    procedimento: Mapped[str | None] = mapped_column(String(300))
    medido_em: Mapped[dt.datetime | None]
    # pico voltamétrico
    e_pico_v: Mapped[float | None] = mapped_column(Float)
    i_pico_ua: Mapped[float | None] = mapped_column(Float)
    i_base_ua: Mapped[float | None] = mapped_column(Float)
    altura_ua: Mapped[float | None] = mapped_column(Float)
    largura_v: Mapped[float | None] = mapped_column(Float)
    area_uav: Mapped[float | None] = mapped_column(Float)
    # a curva inteira (é o que o modelo usa)
    potential_v: Mapped[list]
    current_ua: Mapped[list]
    # controle
    qc_flag: Mapped[str | None] = mapped_column(String(10))
    arquivo: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[dt.datetime] = mapped_column(default=agora)
