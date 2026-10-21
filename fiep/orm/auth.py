"""Usuários da plataforma."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, agora

PAPEIS = ("admin", "colaborador", "leitor")


class Usuario(Base):
    """admin: tudo, inclusive usuários · colaborador: envia e edita dados · leitor: só consulta."""
    __tablename__ = "usuarios"
    __table_args__ = (CheckConstraint(f"papel IN {PAPEIS}", name="papel"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))
    senha_hash: Mapped[str] = mapped_column(String(100))
    papel: Mapped[str] = mapped_column(String(20), default="colaborador")
    instituicao: Mapped[str | None] = mapped_column(String(120))
    ativo: Mapped[bool] = mapped_column(default=True)
    # muda a cada troca de senha/desativação: invalida as sessões abertas
    versao_sessao: Mapped[int] = mapped_column(default=1)
    criado_em: Mapped[dt.datetime] = mapped_column(default=agora)
    ultimo_login: Mapped[dt.datetime | None]

    def __repr__(self) -> str:
        return f"<Usuario {self.email} ({self.papel})>"
