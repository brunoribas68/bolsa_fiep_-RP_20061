"""Modelos: métricas do modelo em uso, comparação de algoritmos, histórico e novos treinos."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from fiep import registro
from fiep.catalogo import DESCRICAO_CLASSIFICADORES, DESCRICAO_REGRESSORES
from fiep.experimentos import DESCRICAO_VARIANTES, VARIANTES
from fiep.orm import Usuario

from ..deps import pode_editar, so_admin, usuario_atual

r = APIRouter(prefix="/api", tags=["modelos"])


class NovoTreino(BaseModel):
    algoritmos: list[str] = Field(default_factory=list, description="vazio = todos")
    variantes: list[str] = Field(default_factory=list, description="vazio = todas")
    empresas: list[int] = Field(default_factory=list, description="vazio = todas")
    com_exemplo: bool = False
    ativar: bool = False
    treino: float = Field(default=0.5, gt=0, lt=1)
    validacao: float = Field(default=0.25, ge=0, lt=1)
    teste: float = Field(default=0.25, ge=0, lt=1)


def _pastas(request: Request):
    cfg = request.app.state.config
    return cfg.modelos, cfg.resultados


@r.get("/catalogo")
def catalogo(_=Depends(usuario_atual)):
    return {
        "algoritmos": [{"id": k, "familia": f, "descricao": t} for k, (f, t) in DESCRICAO_CLASSIFICADORES.items()],
        "variantes": [{"id": k, "descricao": DESCRICAO_VARIANTES.get(k, k)} for k in VARIANTES],
        "regressores": [{"id": k, "descricao": t} for k, t in DESCRICAO_REGRESSORES.items()],
    }


@r.get("/modelos")
def listar(request: Request, _=Depends(usuario_atual)):
    return registro.listar(_pastas(request)[0])


@r.get("/modelos/{mid}")
def detalhe(mid: str, request: Request, _=Depends(usuario_atual)):
    try:
        return registro.detalhe(mid, *_pastas(request))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@r.get("/modelos/{mid}/figuras/{nome}")
def figura(mid: str, nome: str, request: Request, _=Depends(usuario_atual)):
    try:
        return FileResponse(registro.figura(mid, nome, *_pastas(request)), media_type="image/png")
    except FileNotFoundError as e:
        raise HTTPException(404, "Figura não encontrada.") from e


@r.post("/modelos/{mid}/ativar")
def ativar(mid: str, request: Request, _=Depends(so_admin)):
    try:
        registro.ativar(mid, _pastas(request)[0])
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return {"ok": True, "em_uso": mid}


@r.get("/treinos")
def treinos(request: Request, _=Depends(usuario_atual)):
    return request.app.state.treinos.listar()


@r.get("/treinos/{tid}")
def treino(tid: str, request: Request, _=Depends(usuario_atual)):
    d = request.app.state.treinos.obter(tid)
    if d is None:
        raise HTTPException(404, "Treino não encontrado.")
    return d


@r.post("/treinos", status_code=202)
def novo_treino(dados: NovoTreino, request: Request, u: Usuario = Depends(pode_editar)):
    algs = [a for a in dados.algoritmos if a not in DESCRICAO_CLASSIFICADORES]
    vars_ = [v for v in dados.variantes if v not in VARIANTES]
    if algs or vars_:
        raise HTTPException(400, f"Desconhecidos: {algs + vars_}")
    if dados.ativar and u.papel != "admin":
        raise HTTPException(403, "Só administradores trocam o modelo em uso.")
    if abs(dados.treino + dados.validacao + dados.teste - 1) > 0.01:
        raise HTTPException(400, "As proporções de treino, validação e teste precisam somar 100%.")
    params = dados.model_dump()
    params["proporcoes"] = {"treino": dados.treino, "validacao": dados.validacao, "teste": dados.teste}
    try:
        return request.app.state.treinos.iniciar(params, u.nome)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
