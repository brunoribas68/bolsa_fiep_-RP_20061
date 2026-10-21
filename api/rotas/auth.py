"""Login, logout, usuário atual e troca da própria senha."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fiep import usuarios
from fiep.orm import Usuario
from fiep.orm.base import agora

from ..deps import sessao, usuario_atual
from ..seguranca import COOKIE, criar_token

r = APIRouter(prefix="/api/auth", tags=["autenticação"])


class Login(BaseModel):
    email: str = Field(max_length=254)
    senha: str = Field(max_length=200)


class TrocaSenha(BaseModel):
    atual: str = Field(max_length=200)
    nova: str = Field(max_length=200)


def perfil(u: Usuario) -> dict:
    return {"id": u.id, "email": u.email, "nome": u.nome, "papel": u.papel, "instituicao": u.instituicao,
            "ativo": u.ativo, "ultimo_login": u.ultimo_login.isoformat() if u.ultimo_login else None,
            "criado_em": u.criado_em.isoformat() if u.criado_em else None}


def _cookie(resp: Response, request: Request, u: Usuario) -> None:
    cfg = request.app.state.config
    resp.set_cookie(COOKIE, criar_token(u.id, u.versao_sessao, cfg.segredo, cfg.sessao_horas),
                    max_age=int(cfg.sessao_horas * 3600), httponly=True, samesite="strict",
                    secure=cfg.cookie_seguro, path="/")


@r.post("/login")
def login(dados: Login, request: Request, response: Response, s: Session = Depends(sessao)):
    limite = request.app.state.limite
    ip = request.client.host if request.client else "?"
    chaves = (f"ip:{ip}", f"email:{dados.email.strip().lower()}")
    if limite.bloqueado(*chaves):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    u = usuarios.por_email(s, dados.email)
    ok = usuarios.confere_senha(dados.senha, u.senha_hash if u else usuarios.HASH_FALSO)
    if not (u and ok and u.ativo):
        limite.falhou(*chaves)
        raise HTTPException(401, "E-mail ou senha incorretos.")
    limite.sucesso(*chaves)
    u.ultimo_login = agora()
    s.commit()
    _cookie(response, request, u)
    return perfil(u)


@r.post("/sair")
def sair(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@r.get("/eu")
def eu(u: Usuario = Depends(usuario_atual)):
    return perfil(u)


@r.post("/senha")
def trocar_senha(dados: TrocaSenha, request: Request, response: Response,
                 u: Usuario = Depends(usuario_atual), s: Session = Depends(sessao)):
    if not usuarios.confere_senha(dados.atual, u.senha_hash):
        raise HTTPException(400, "A senha atual não confere.")
    u = s.merge(u)
    try:
        usuarios.trocar_senha(s, u, dados.nova)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    _cookie(response, request, u)          # a sessão atual continua; as outras caem
    return {"ok": True}
