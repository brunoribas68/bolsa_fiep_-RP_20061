"""Modelos: o modelo em uso, a comparação de algoritmos e representações, o histórico e novos treinos."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from fiep import modelagem
from fiep.catalogo import INFO_CLASSIFICADORES
from fiep.orm import Usuario

from ..deps import pode_editar, so_admin, usuario_atual

r = APIRouter(prefix="/api", tags=["modelos"])


class NovoTreino(BaseModel):
    algoritmos: list[str] = Field(default_factory=list, description="vazio = todos")
    variantes: list[str] = Field(default_factory=list, description="representações da curva; vazio = todas")
    empresas: list[int] = Field(default_factory=list, description="vazio = todas")
    ativar: bool = False


@r.get("/catalogo")
def catalogo(_=Depends(usuario_atual)):
    """Algoritmos e representações com nome legível e explicação (tooltips da plataforma)."""
    return {
        "algoritmos": [{"id": k, **v, "descricao": f"{v['nome']} — {v['ajuste']}"} for k, v in INFO_CLASSIFICADORES.items()],
        "variantes": [{"id": k, **v, "descricao": v["o_que"]} for k, v in modelagem.INFO_VARIANTES.items()],
        "ba_confiavel": modelagem.BA_CONFIAVEL,
    }


@r.get("/modelos")
def listar(request: Request, _=Depends(usuario_atual)):
    return modelagem.listar(request.app.state.config.modelos)


@r.get("/modelos/{mid}")
def detalhe(mid: str, request: Request, _=Depends(usuario_atual)):
    pasta = request.app.state.config.modelos
    try:
        return {**modelagem.cartao(mid, pasta), "em_uso": modelagem.em_uso(pasta) == mid}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@r.post("/modelos/{mid}/ativar")
def ativar(mid: str, request: Request, _=Depends(so_admin)):
    try:
        modelagem.ativar_modelo(mid, request.app.state.config.modelos)
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
    desconhecidos = [a for a in dados.algoritmos if a not in INFO_CLASSIFICADORES] + \
                    [v for v in dados.variantes if v not in modelagem.INFO_VARIANTES]
    if desconhecidos:
        raise HTTPException(400, f"Desconhecidos: {desconhecidos}")
    if dados.ativar and u.papel != "admin":
        raise HTTPException(403, "Só administradores trocam o modelo em uso.")
    try:
        return request.app.state.treinos.iniciar(dados.model_dump(), u.nome)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
