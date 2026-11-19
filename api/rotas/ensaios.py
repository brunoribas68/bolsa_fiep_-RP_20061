"""Ensaios: a base do genossensor (um voltamograma por linha), com edição dos campos."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fiep import genossensor
from fiep.orm import Ensaio
from fiep.orm.genossensor import QC, TIPOS

from ..deps import pode_editar, sessao, usuario_atual
from ..modelo import limpo, registros

r = APIRouter(prefix="/api/ensaios", tags=["ensaios"])

COLUNAS_LISTA = ["id", "arquivo", "empresa_id", "coleta_id", "eletrodo_id", "canal", "elemento_captura", "tipo",
                 "bacteria", "concentracao", "e_pico_v", "i_pico_ua", "altura_ua", "branco_id", "queda_pct",
                 "abaixo_do_branco", "qc_flag", "medido_em", "observacoes"]


class EdicaoEnsaio(BaseModel):
    tipo: str | None = Field(default=None, pattern=f"^({'|'.join(TIPOS)})$")
    concentracao: float | None = Field(default=None, ge=0)
    eletrodo_id: str | None = Field(default=None, min_length=1, max_length=60)
    elemento_captura: str | None = Field(default=None, max_length=120)
    bacteria: str | None = Field(default=None, max_length=120)
    qc_flag: str | None = Field(default=None, pattern=f"^({'|'.join(QC)})?$")
    observacoes: str | None = Field(default=None, max_length=2000)


@r.get("")
def listar(empresa_id: int | None = None, coleta_id: int | None = None, s: Session = Depends(sessao),
           _=Depends(usuario_atual)):
    df = genossensor.tabela(s, empresa_id=empresa_id, coleta_id=coleta_id)
    return {"ensaios": registros(df[COLUNAS_LISTA]) if len(df) else [],
            "calibracao": genossensor.calibracao(df) if len(df) else None}


@r.get("/{eid}")
def detalhe(eid: int, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    e = s.get(Ensaio, eid)
    if e is None:
        raise HTTPException(404, "Ensaio não encontrado.")
    out = {c.name: limpo(getattr(e, c.name)) for c in Ensaio.__table__.columns}
    out["medido_em"] = e.medido_em.isoformat() if e.medido_em else None
    out["criado_em"] = e.criado_em.isoformat()
    branco = s.get(Ensaio, e.branco_id) if e.branco_id else None
    out["queda_pct"] = (100 * (branco.altura_ua - e.altura_ua) / branco.altura_ua
                        if branco and branco.altura_ua and e.altura_ua is not None else None)
    out["branco"] = ({"id": branco.id, "arquivo": branco.arquivo, "altura_ua": branco.altura_ua,
                      "potential_v": branco.potential_v, "current_ua": branco.current_ua} if branco else None)
    return out


@r.patch("/{eid}")
def editar(eid: int, dados: EdicaoEnsaio, s: Session = Depends(sessao), _=Depends(pode_editar)):
    e = s.get(Ensaio, eid)
    if e is None:
        raise HTTPException(404, "Ensaio não encontrado.")
    mud = dados.model_dump(exclude_unset=True)
    for k, v in mud.items():
        setattr(e, k, (v.strip() or None) if isinstance(v, str) else v)
    if e.tipo == "branco":
        e.concentracao, e.branco_id = 0.0, None
    elif not e.concentracao:
        raise HTTPException(400, "Um ensaio de RNA precisa da concentração (ng/mL).")
    if {"tipo", "eletrodo_id", "elemento_captura"} & set(mud):
        e.branco_id = None if e.tipo == "rna" else e.branco_id
        s.flush()
        genossensor.ligar_brancos(s)
    s.commit()
    return detalhe(eid, s, _)


@r.delete("/{eid}")
def apagar(eid: int, s: Session = Depends(sessao), _=Depends(pode_editar)):
    e = s.get(Ensaio, eid)
    if e is None:
        raise HTTPException(404, "Ensaio não encontrado.")
    s.delete(e)
    s.commit()
    return {"ok": True}
