"""Plataforma FIEP: API (FastAPI) + frontend React (web/), com login.

Rodar (da raiz do repositório):
    fiep servir                              # http://127.0.0.1:8000 (serve também o frontend compilado)
    uvicorn api.app:app --reload             # alternativa
    cd web && npm run dev                    # frontend em modo desenvolvimento (proxy para a API)

Primeiro acesso: crie um admin com `fiep usuario criar --email voce@... --papel admin`
(ou FIEP_ADMIN_EMAIL/FIEP_ADMIN_SENHA no primeiro start). Configuração: api/config.py.
Documentação interativa: /docs.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from fiep import __version__, usuarios
from fiep.orm import Usuario, fabrica_sessoes, migrar

from .config import Config
from .modelo import ModeloAtual
from .rotas import amostras, auth, coletas, empresas, painel, previsao
from .rotas import usuarios as rotas_usuarios
from .seguranca import CABECALHO_CSRF, LimiteTentativas

log = logging.getLogger("fiep.api")
WEB = Path(__file__).resolve().parent.parent / "web" / "dist"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _primeiro_admin(cfg: Config, sessoes) -> None:
    import os
    with sessoes() as s:
        if s.scalar(select(func.count()).select_from(Usuario)):
            return
        email, senha = os.environ.get("FIEP_ADMIN_EMAIL"), os.environ.get("FIEP_ADMIN_SENHA")
        if email and senha:
            usuarios.criar(s, email, "Administrador", senha, "admin")
            log.warning("Admin inicial %s criado a partir de FIEP_ADMIN_EMAIL.", email)
        else:
            log.warning("Nenhum usuário cadastrado: crie um admin com "
                        "`fiep usuario criar --email voce@exemplo.org --papel admin`.")


def criar_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config.do_ambiente()

    @asynccontextmanager
    async def ciclo(app: FastAPI):
        migrar(cfg.db_url, dados_exemplo=cfg.dados_exemplo)
        _primeiro_admin(cfg, app.state.sessoes)
        yield

    app = FastAPI(title="Plataforma FIEP", version=__version__, lifespan=ciclo,
                  description="Coletas de voltamogramas, banco de amostras e previsão de contaminação.")
    app.state.config = cfg
    app.state.sessoes = fabrica_sessoes(cfg.db_url)
    app.state.limite = LimiteTentativas()
    app.state.modelo = ModeloAtual(cfg.modelos, cfg.config_pipeline)

    @app.middleware("http")
    async def protecoes(request: Request, call_next):
        # CSRF: alterações na API só com o cabeçalho que formulários de outros sites não conseguem mandar
        if request.url.path.startswith("/api/") and request.method not in METODOS_SEGUROS:
            nome, valor = CABECALHO_CSRF
            if request.headers.get(nome, "").lower() != valor:
                return JSONResponse({"detail": "Requisição recusada (cabeçalho de proteção ausente)."}, 403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
            resp.headers.setdefault("Content-Security-Policy",
                                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                    "font-src 'self' data:; script-src 'self'; frame-ancestors 'none'")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    for m in (auth, rotas_usuarios, empresas, coletas, amostras, previsao, painel):
        app.include_router(m.r)

    if WEB.exists():
        app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

        @app.get("/{caminho:path}", include_in_schema=False)
        def spa(caminho: str):
            if caminho.startswith("api/"):
                return JSONResponse({"detail": "Rota não encontrada."}, 404)
            arq = (WEB / caminho).resolve()
            if caminho and arq.is_file() and str(arq).startswith(str(WEB)):
                return FileResponse(arq)
            return FileResponse(WEB / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def sem_frontend():
            return JSONResponse({"detail": "Frontend não compilado: rode `cd web && npm install && npm run build`. "
                                           "A API está em /docs."})
    return app


app = criar_app()
