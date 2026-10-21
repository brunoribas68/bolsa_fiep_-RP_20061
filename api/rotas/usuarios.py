"""Gestão de usuários (só admin). Não há cadastro aberto: o admin cria as contas."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fiep import usuarios
from fiep.orm import Usuario
from fiep.orm.auth import PAPEIS

from ..deps import sessao, so_admin
from .auth import perfil

r = APIRouter(prefix="/api/usuarios", tags=["usuários"])


class NovoUsuario(BaseModel):
    email: str = Field(max_length=254)
    nome: str = Field(min_length=1, max_length=120)
    senha: str = Field(max_length=200)
    papel: str = "colaborador"
    instituicao: str | None = Field(default=None, max_length=120)


class EdicaoUsuario(BaseModel):
    nome: str | None = Field(default=None, max_length=120)
    papel: str | None = None
    instituicao: str | None = Field(default=None, max_length=120)
    ativo: bool | None = None


class NovaSenha(BaseModel):
    nova: str = Field(max_length=200)


@r.get("")
def listar(s: Session = Depends(sessao), _=Depends(so_admin)):
    return [perfil(u) for u in s.scalars(select(Usuario).order_by(Usuario.nome))]


@r.post("", status_code=201)
def criar(dados: NovoUsuario, s: Session = Depends(sessao), _=Depends(so_admin)):
    try:
        return perfil(usuarios.criar(s, dados.email, dados.nome, dados.senha, dados.papel, dados.instituicao))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _admins_ativos(s: Session) -> int:
    return s.scalar(select(func.count()).select_from(Usuario).where(Usuario.papel == "admin", Usuario.ativo))


@r.patch("/{uid}")
def editar(uid: int, dados: EdicaoUsuario, s: Session = Depends(sessao), eu: Usuario = Depends(so_admin)):
    u = s.get(Usuario, uid)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    if dados.papel is not None and dados.papel not in PAPEIS:
        raise HTTPException(400, f"Papel inválido (use {', '.join(PAPEIS)}).")
    perde_admin = u.papel == "admin" and u.ativo and (dados.ativo is False or (dados.papel and dados.papel != "admin"))
    if perde_admin and _admins_ativos(s) <= 1:
        raise HTTPException(400, "É preciso manter pelo menos um administrador ativo.")
    for campo in ("nome", "papel", "instituicao", "ativo"):
        v = getattr(dados, campo)
        if v is not None:
            setattr(u, campo, v)
    if dados.ativo is False or dados.papel is not None:
        u.versao_sessao += 1                 # mudança de acesso vale na hora
    s.commit()
    return perfil(u)


@r.post("/{uid}/senha")
def redefinir_senha(uid: int, dados: NovaSenha, s: Session = Depends(sessao), _=Depends(so_admin)):
    u = s.get(Usuario, uid)
    if u is None:
        raise HTTPException(404, "Usuário não encontrado.")
    try:
        usuarios.trocar_senha(s, u, dados.nova)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}
