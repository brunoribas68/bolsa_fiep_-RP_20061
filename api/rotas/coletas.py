"""Coletas: cada envio de dados das empresas (arquivos .nox/Excel + rótulos das amostras)."""
from __future__ import annotations

import datetime as dt
import json
import logging
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from fiep import db
from fiep.config import load_config
from fiep.ingest import ingerir
from fiep.orm import Amostra, Arquivo, Coleta, Empresa, Medicao, Plaqueamento, Usuario
from fiep.orm.cadastro import CONJUNTOS
from fiep.qc import avaliar

from .. import arquivos as up
from ..deps import pode_editar, sessao, so_admin, usuario_atual
from ..modelo import registros

log = logging.getLogger(__name__)
r = APIRouter(prefix="/api/coletas", tags=["coletas"])


class AmostraInformada(BaseModel):
    sample_id: str = Field(min_length=1, max_length=120)
    contamination_status: int | None = Field(default=None, ge=0, le=1)
    sample_log10_mean_cfu_ml: float | None = Field(default=None, ge=-1, le=15)
    target_bacterium: str | None = Field(default=None, max_length=120)
    surface_type: str | None = Field(default=None, max_length=120)
    observacoes: str | None = Field(default=None, max_length=2000)


def resumo_coleta(s: Session, c: Coleta) -> dict:
    sem_rotulo = s.scalar(select(func.count()).select_from(Amostra).where(
        Amostra.coleta_id == c.id, Amostra.contamination_status.is_(None)))
    autor = s.get(Usuario, c.criado_por_id) if c.criado_por_id else None
    return {"id": c.id, "empresa_id": c.empresa_id, "empresa": c.empresa.nome if c.empresa else None,
            "descricao": c.descricao, "data_coleta": c.data_coleta.isoformat() if c.data_coleta else None,
            "conjunto": c.conjunto, "n_amostras": c.n_amostras, "n_medicoes": c.n_medicoes,
            "amostras_sem_rotulo": sem_rotulo, "avisos": c.avisos or [], "origem": c.origem,
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
    arqs = [{"arquivo": a.arquivo, "papel": a.papel, "tamanho_bytes": a.tamanho_bytes, "sha256": a.sha256[:12]}
            for a in c.arquivos]
    rep = db.sql(s, "SELECT r.* FROM v_replicatas r JOIN amostras a ON a.sample_id = r.sample_id "
                    "WHERE a.coleta_id = ? ORDER BY r.sample_id, r.replicate_id", (cid,))
    return {**resumo_coleta(s, c), "arquivos": arqs, "replicas": registros(rep)}


@r.post("", status_code=201)
async def criar(request: Request,
                arquivos: list[UploadFile] = File(..., description=".nox, Excel/CSV do NOVA, planilhas"),
                caminhos: list[str] = Form(default=[], description="caminho relativo de cada arquivo (amostra/arquivo)"),
                empresa_id: int | None = Form(default=None), descricao: str | None = Form(default=None),
                data_coleta: dt.date | None = Form(default=None), conjunto: str | None = Form(default=None),
                amostras: str | None = Form(default=None, description="JSON: lista de amostras com o rótulo"),
                s: Session = Depends(sessao), u: Usuario = Depends(pode_editar)):
    app = request.app
    conjunto = conjunto or None
    if conjunto and conjunto not in CONJUNTOS:
        raise HTTPException(400, f"Conjunto inválido (use {', '.join(CONJUNTOS)} ou deixe vazio).")
    if empresa_id is not None and s.get(Empresa, empresa_id) is None:
        raise HTTPException(400, "Empresa não encontrada.")
    try:
        informadas = [AmostraInformada(**a) for a in json.loads(amostras)] if amostras else []
    except (json.JSONDecodeError, TypeError, ValidationError) as e:
        raise HTTPException(400, f"Lista de amostras inválida: {e}") from e

    coleta = Coleta(empresa_id=empresa_id, descricao=(descricao or "").strip() or None, data_coleta=data_coleta,
                    conjunto=conjunto, origem="plataforma", criado_por_id=u.id)
    s.add(coleta)
    s.flush()
    pasta = app.state.config.armazenamento / f"coleta_{coleta.id:05d}"
    try:
        salvos = await up.salvar(arquivos, pasta, caminhos)
        cfg = load_config(app.state.config.config_pipeline)
        try:
            ds = ingerir(pasta, cfg=cfg)
        except FileNotFoundError as e:
            raise HTTPException(400, "Nenhum voltamograma encontrado nos arquivos (.nox ou Excel/CSV do NOVA).") from e
        ids = set(ds.medicoes["sample_id"].dropna().astype(str))
        outras = s.scalars(select(Amostra.sample_id).where(Amostra.sample_id.in_(ids),
                                                           Amostra.coleta_id != coleta.id)).all()
        if outras:
            raise HTTPException(409, "Já existem amostras com estes códigos em outra coleta: "
                                     f"{', '.join(sorted(outras)[:10])}. Use outros códigos.")
        if conjunto:
            ds.medicoes["conjunto"] = conjunto
        res = db.importar(s, ds, origem="plataforma", coleta=coleta, conjunto=conjunto, usuario_id=u.id,
                          caminhos={p.name: str(p) for p in salvos})
        db.gravar_qc(s, avaliar(ds.medicoes, ds.pontos, cfg))
        for a in informadas:                     # rótulo e carga informados no formulário
            am = s.get(Amostra, a.sample_id.strip())
            if am is None:
                continue
            for k, v in a.model_dump(exclude={"sample_id"}).items():
                if v is not None:
                    setattr(am, k, v.strip() if isinstance(v, str) else v)
            am.atualizado_por_id = u.id
        s.commit()
    except Exception:
        s.rollback()
        shutil.rmtree(pasta, ignore_errors=True)
        c = s.get(Coleta, coleta.id)
        if c is not None and not s.scalar(select(func.count()).select_from(Medicao).where(Medicao.coleta_id == c.id)):
            s.delete(c)
            s.commit()
        raise
    log.info("Coleta %s: %s medições de %s amostras enviadas por %s", coleta.id, res["medicoes"], res["amostras"],
             u.email)
    s.refresh(coleta)
    return {**detalhe(coleta.id, s, u), "importacao": res}


@r.delete("/{cid}")
def apagar(cid: int, request: Request, s: Session = Depends(sessao), _=Depends(so_admin)):
    c = s.get(Coleta, cid)
    if c is None:
        raise HTTPException(404, "Coleta não encontrada.")
    amostras = select(Amostra.sample_id).where(Amostra.coleta_id == cid)
    s.execute(delete(Medicao).where(Medicao.coleta_id == cid))
    s.execute(delete(Medicao).where(Medicao.sample_id.in_(amostras)))
    s.execute(delete(Plaqueamento).where(Plaqueamento.sample_id.in_(amostras)))
    s.execute(delete(Amostra).where(Amostra.coleta_id == cid))
    s.execute(delete(Arquivo).where(Arquivo.coleta_id == cid))
    s.delete(c)
    s.commit()
    shutil.rmtree(request.app.state.config.armazenamento / f"coleta_{cid:05d}", ignore_errors=True)
    return {"ok": True}
