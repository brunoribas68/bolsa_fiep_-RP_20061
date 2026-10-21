"""Contas de usuário: senha com bcrypt e criação pela linha de comando.

    fiep usuario criar --email ana@fiep.org --nome "Ana" --papel admin     # pede a senha
    fiep usuario listar
    fiep usuario senha --email ana@fiep.org                                # redefine a senha
    fiep usuario desativar --email ana@fiep.org
"""
from __future__ import annotations

import re

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .orm import Usuario
from .orm.auth import PAPEIS

MIN_SENHA = 10


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def confere_senha(senha: str, senha_hash: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode())
    except ValueError:
        return False


# hash de referência: comparar contra ele quando o usuário não existe gasta o mesmo tempo
# (não revela, pelo tempo de resposta, quais e-mails têm conta)
HASH_FALSO = hash_senha("senha-que-ninguem-tem")


def validar_senha(senha: str, email: str = "") -> str | None:
    """Mensagem de erro, ou None se a senha é aceitável."""
    if len(senha) < MIN_SENHA:
        return f"A senha precisa ter pelo menos {MIN_SENHA} caracteres."
    if len(senha.encode("utf-8")) > 72:
        return "A senha pode ter no máximo 72 bytes."
    if email and senha.lower() == email.lower():
        return "A senha não pode ser igual ao e-mail."
    if len(set(senha)) < 4:
        return "A senha é repetitiva demais."
    return None


def validar_email(email: str) -> str | None:
    return None if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or "") else "E-mail inválido."


def criar(s: Session, email: str, nome: str, senha: str, papel: str = "colaborador",
          instituicao: str | None = None) -> Usuario:
    email = email.strip().lower()
    for erro in (validar_email(email), validar_senha(senha, email)):
        if erro:
            raise ValueError(erro)
    if papel not in PAPEIS:
        raise ValueError(f"Papel inválido: {papel} (use {', '.join(PAPEIS)})")
    if s.scalar(select(Usuario).where(func.lower(Usuario.email) == email)):
        raise ValueError(f"Já existe um usuário com o e-mail {email}.")
    u = Usuario(email=email, nome=nome.strip(), senha_hash=hash_senha(senha), papel=papel, instituicao=instituicao)
    s.add(u)
    s.commit()
    return u


def trocar_senha(s: Session, u: Usuario, nova: str) -> None:
    erro = validar_senha(nova, u.email)
    if erro:
        raise ValueError(erro)
    u.senha_hash = hash_senha(nova)
    u.versao_sessao += 1                      # derruba as sessões abertas
    s.commit()


def por_email(s: Session, email: str) -> Usuario | None:
    return s.scalar(select(Usuario).where(func.lower(Usuario.email) == (email or "").strip().lower()))
