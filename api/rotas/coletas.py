"""Coletas: cada envio de .nox (branco e RNA) pela plataforma."""
from __future__ import annotations

import datetime as dt
import logging
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from fiep import genossensor
from fiep.orm import Coleta, Empresa, Ensaio, Usuario

from .. import arquivos as up
from ..deps import pode_editar, sessao, so_admin, usuario_atual
from ..modelo import registros
from .ensaios import COLUNAS_LISTA

log = logging.getLogger(__name__)
r = APIRouter(prefix="/api/coletas", tags=["coletas"])


def resumo_coleta(s: Session, c: Coleta) -> dict:
    autor = s.get(Usuario, c.criado_por_id) if c.criado_por_id else None
    tipos = dict(s.execute(select(Ensaio.tipo, func.count()).where(Ensaio.coleta_id == c.id)
                           .group_by(Ensaio.tipo)).all())
    return {"id": c.id, "empresa_id": c.empresa_id, "empresa": c.empresa.nome if c.empresa else None,
            "descricao": c.descricao, "data_coleta": c.data_coleta.isoformat() if c.data_coleta else None,
            "n_ensaios": c.n_ensaios, "n_branco": tipos.get("branco", 0), "n_rna": tipos.get("rna", 0),
            "avisos": c.avisos or [], "origem": c.origem,
            "criado_por": autor.nome if autor else None, "criado_em": c.criado_em.isoformat()}


@r.get("")
def listar(empresa_id: int | None = None, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    q = select(Coleta).order_by(Coleta.criado_em.desc())
    if empresa_id:
        q = q.where(Coleta.empresa_id == empresa_id)
    return [resumo_coleta(s, c) for c in s.scalars(q)]


@r.get("/{cid}")
def detalhe(cid: int, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    c = s.get(Coleta, cid)
    if c is None:
        raise HTTPException(404, "Coleta não encontrada.")
    df = genossensor.tabela(s, coleta_id=cid)
    return {**resumo_coleta(s, c), "ensaios": registros(df[COLUNAS_LISTA]) if len(df) else []}


@r.post("", status_code=201)
async def criar(request: Request,
                arquivos: list[UploadFile] = File(..., description=".nox de branco (dpv-branco-Ej) e de RNA (dpv-RNA-<conc>-Ej)"),
                caminhos: list[str] = Form(default=[], description="caminho relativo de cada arquivo (contaminado/..., nao_contaminado/...)"),
                empresa_id: int | None = Form(default=None), descricao: str | None = Form(default=None),
                data_coleta: dt.date | None = Form(default=None),
                elemento: str | None = Form(default=None, description="elemento de captura de quem não tiver no procedimento"),
                bacteria: str | None = Form(default=None),
                s: Session = Depends(sessao), u: Usuario = Depends(pode_editar)):
    if empresa_id is not None and s.get(Empresa, empresa_id) is None:
        raise HTTPException(400, "Empresa não encontrada.")
    coleta = Coleta(empresa_id=empresa_id, descricao=(descricao or "").strip() or None, data_coleta=data_coleta,
                    origem="plataforma", criado_por_id=u.id)
    s.add(coleta)
    s.flush()
    pasta = request.app.state.config.armazenamento / f"coleta_{coleta.id:05d}"
    try:
        salvos = await up.salvar(arquivos, pasta, caminhos)
        if not any(p.suffix.lower() == ".nox" for p in salvos):
            raise HTTPException(400, "Envie os voltamogramas em .nox (dpv-branco-E1.nox, dpv-RNA-0,1-E1.nox...).")
        res = genossensor.importar(s, pasta, empresa_id=empresa_id, coleta=coleta, elemento=elemento or None,
                                   bacteria=bacteria or None, usuario_id=u.id)
        if not res["gravados"]:
            motivo = "; ".join(res["avisos"][:5]) or "os arquivos já estavam no banco"
            raise HTTPException(400, f"Nenhum ensaio novo foi gravado: {motivo}")
    except Exception:
        s.rollback()
        shutil.rmtree(pasta, ignore_errors=True)
        c = s.get(Coleta, coleta.id)
        if c is not None:
            s.delete(c)
            s.commit()
        raise
    log.info("Coleta %s: %s ensaio(s) enviado(s) por %s", coleta.id, res["gravados"], u.email)
    s.refresh(coleta)
    return {**detalhe(coleta.id, s, u), "importacao": res}


@r.delete("/{cid}")
def apagar(cid: int, request: Request, s: Session = Depends(sessao), _=Depends(so_admin)):
    c = s.get(Coleta, cid)
    if c is None:
        raise HTTPException(404, "Coleta não encontrada.")
    s.execute(delete(Ensaio).where(Ensaio.coleta_id == cid))
    s.delete(c)
    s.commit()
    shutil.rmtree(request.app.state.config.armazenamento / f"coleta_{cid:05d}", ignore_errors=True)
    return {"ok": True}
