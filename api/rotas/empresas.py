"""Empresas (onde as coletas são feitas)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fiep.orm import Amostra, Coleta, Empresa

from ..deps import pode_editar, sessao, usuario_atual

r = APIRouter(prefix="/api/empresas", tags=["empresas"])


class DadosEmpresa(BaseModel):
    nome: str = Field(min_length=1, max_length=160)
    cidade: str | None = Field(default=None, max_length=120)
    segmento: str | None = Field(default=None, max_length=120)
    observacoes: str | None = Field(default=None, max_length=2000)


def _json(e: Empresa, n_coletas=0, n_amostras=0) -> dict:
    return {"id": e.id, "nome": e.nome, "cidade": e.cidade, "segmento": e.segmento, "observacoes": e.observacoes,
            "n_coletas": n_coletas, "n_amostras": n_amostras}


@r.get("")
def listar(s: Session = Depends(sessao), _=Depends(usuario_atual)):
    nc = dict(s.execute(select(Coleta.empresa_id, func.count()).group_by(Coleta.empresa_id)).all())
    na = dict(s.execute(select(Amostra.empresa_id, func.count()).group_by(Amostra.empresa_id)).all())
    return [_json(e, nc.get(e.id, 0), na.get(e.id, 0)) for e in s.scalars(select(Empresa).order_by(Empresa.nome))]


@r.post("", status_code=201)
def criar(dados: DadosEmpresa, s: Session = Depends(sessao), _=Depends(pode_editar)):
    if s.scalar(select(Empresa).where(func.lower(Empresa.nome) == dados.nome.strip().lower())):
        raise HTTPException(409, "Já existe uma empresa com esse nome.")
    e = Empresa(**{**dados.model_dump(), "nome": dados.nome.strip()})
    s.add(e)
    s.commit()
    return _json(e)


@r.patch("/{eid}")
def editar(eid: int, dados: DadosEmpresa, s: Session = Depends(sessao), _=Depends(pode_editar)):
    e = s.get(Empresa, eid)
    if e is None:
        raise HTTPException(404, "Empresa não encontrada.")
    for k, v in dados.model_dump().items():
        setattr(e, k, v.strip() if isinstance(v, str) else v)
    s.commit()
    return _json(e)
