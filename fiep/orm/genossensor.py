"""Base do genossensor: uma linha por medição DPV (branco ou alvo), com o pico já extraído.

Dicionário completo: docs/DICIONARIO_DADOS.md. Mantém as tabelas de empresas, coletas e usuários;
o resto (amostras/medicoes/curvas) é da base antiga (case).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, agora
from .cadastro import CONJUNTOS

# branco: só o elemento de captura; alvo: depois do RNA; negativo: amostra sem o RNA-alvo
TIPOS = ("branco", "alvo", "negativo")


class Ensaio(Base):
    __tablename__ = "ensaios"
    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS}", name="tipo"),
        CheckConstraint("concentracao >= 0", name="concentracao"),
        CheckConstraint("tipo = 'alvo' OR concentracao = 0", name="sem_alvo_conc_zero"),
        CheckConstraint(f"conjunto IS NULL OR conjunto IN {CONJUNTOS}", name="conjunto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresas.id"), index=True)
    coleta_id: Mapped[int | None] = mapped_column(ForeignKey("coletas.id", ondelete="SET NULL"), index=True)
    # identificação
    eletrodo_id: Mapped[str] = mapped_column(String(60), index=True)
    canal: Mapped[str | None] = mapped_column(String(60))
    # o que está no eletrodo
    elemento_captura: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(10))
    alvo: Mapped[str | None] = mapped_column(String(120))
    bacteria: Mapped[str | None] = mapped_column(String(120))
    concentracao: Mapped[float] = mapped_column(Float, default=0.0)
    unidade: Mapped[str] = mapped_column(String(20), default="ng/mL")
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
    # curva inteira (para refazer o pico ou treinar com a curva)
    potential_v: Mapped[list | None]
    current_ua: Mapped[list | None]
    # controle
    qc_flag: Mapped[str | None] = mapped_column(String(20))
    conjunto: Mapped[str | None] = mapped_column(String(20))
    arquivo: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[dt.datetime] = mapped_column(default=agora)
