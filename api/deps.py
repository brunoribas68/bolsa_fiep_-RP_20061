"""Dependências comuns: sessão do banco, usuário logado e checagem de papel."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from fiep.orm import Usuario

from .seguranca import COOKIE, ler_token


def sessao(request: Request) -> Iterator[Session]:
    s = request.app.state.sessoes()
    try:
        yield s
    finally:
        s.close()


def usuario_atual(request: Request, s: Session = Depends(sessao)) -> Usuario:
    token = request.cookies.get(COOKIE)
    dados = ler_token(token, request.app.state.config.segredo) if token else None
    if not dados:
        raise HTTPException(401, "Faça login para continuar.")
    u = s.get(Usuario, int(dados["sub"]))
    if u is None or not u.ativo or u.versao_sessao != dados.get("v"):
        raise HTTPException(401, "Sessão encerrada. Faça login de novo.")
    return u


def exigir(*papeis: str):
    """Dependência que só deixa passar os papéis indicados (admin sempre passa)."""
    def _dep(u: Usuario = Depends(usuario_atual)) -> Usuario:
        if u.papel != "admin" and u.papel not in papeis:
            raise HTTPException(403, "Seu perfil não tem permissão para esta ação.")
        return u
    return _dep


pode_editar = exigir("colaborador")
so_admin = exigir()
