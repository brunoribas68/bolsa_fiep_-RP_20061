"""Amostras: lista com filtros, edição do rótulo, curvas e previsão pelo modelo."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from fiep import db
from fiep.orm import Amostra, Curva, Empresa, Medicao, Plaqueamento, Predicao, Usuario
from fiep.orm.cadastro import CONJUNTOS
from fiep.predict import prever, resumo_por_amostra

from ..deps import pode_editar, sessao, usuario_atual
from ..modelo import limpo, registros

r = APIRouter(prefix="/api", tags=["amostras"])



class EdicaoAmostra(BaseModel):
    contamination_status: int | None = Field(default=None, ge=0, le=1)
    sample_log10_mean_cfu_ml: float | None = Field(default=None, ge=-1, le=15)
    target_bacterium: str | None = Field(default=None, max_length=120)
    surface_type: str | None = Field(default=None, max_length=120)
    conjunto: str | None = None
    observacoes: str | None = Field(default=None, max_length=2000)


class EdicaoMedicao(BaseModel):
    sensor_state: str | None = None
    replicate_id: str | None = Field(default=None, max_length=40)
    qc_flag: str | None = None


_LISTA = """
SELECT a.sample_id, a.empresa_id, e.nome AS empresa, a.coleta_id, a.contamination_status,
       a.sample_log10_mean_cfu_ml, a.target_bacterium, a.surface_type, a.conjunto, a.atualizado_em,
       COALESCE(r.n_replicas, 0) AS n_replicas, COALESCE(r.n_completas, 0) AS n_completas,
       COALESCE(r.n_medicoes, 0) AS n_medicoes,
       (SELECT p.resultado FROM predicoes p WHERE p.sample_id = a.sample_id AND p.status = 'amostra'
        ORDER BY p.previsto_em DESC, p.id DESC LIMIT 1) AS ultima_previsao
FROM amostras a
LEFT JOIN empresas e ON e.id = a.empresa_id
LEFT JOIN (SELECT sample_id, COUNT(*) AS n_replicas, SUM(n_medicoes) AS n_medicoes,
                  SUM(CASE WHEN n_aprovadas >= 3 THEN 1 ELSE 0 END) AS n_completas
           FROM v_replicatas GROUP BY sample_id) r ON r.sample_id = a.sample_id
"""


@r.get("/amostras")
def listar(empresa_id: int | None = None, coleta_id: int | None = None, rotulo: str | None = None,
           conjunto: str | None = None, q: str | None = None, pagina: int = 1, por_pagina: int = 50,
           s: Session = Depends(sessao), _=Depends(usuario_atual)):
    cond, p = [], []
    if empresa_id:
        cond.append("a.empresa_id = ?"), p.append(empresa_id)
    if coleta_id:
        cond.append("a.coleta_id = ?"), p.append(coleta_id)
    if rotulo in ("0", "1"):
        cond.append("a.contamination_status = ?"), p.append(int(rotulo))
    elif rotulo == "sem":
        cond.append("a.contamination_status IS NULL")
    if conjunto == "sorteio":
        cond.append("a.conjunto IS NULL")
    elif conjunto in CONJUNTOS:
        cond.append("a.conjunto = ?"), p.append(conjunto)
    if q:
        cond.append("LOWER(a.sample_id) LIKE ?"), p.append(f"%{q.strip().lower()}%")
    onde = (" WHERE " + " AND ".join(cond)) if cond else ""
    total = int(db.sql(s, f"SELECT COUNT(*) FROM amostras a{onde}", tuple(p)).iloc[0, 0])
    por_pagina = max(1, min(por_pagina, 200))
    pagina = max(1, pagina)
    itens = db.sql(s, f"{_LISTA}{onde} ORDER BY a.sample_id LIMIT ? OFFSET ?",
                   (*p, por_pagina, (pagina - 1) * por_pagina))
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "itens": registros(itens)}


def _amostra(s: Session, sid: str) -> Amostra:
    a = s.get(Amostra, sid)
    if a is None:
        raise HTTPException(404, "Amostra não encontrada.")
    return a


@r.get("/protocolos")
def protocolos(_=Depends(usuario_atual)):
    """Protocolos de biossensor conhecidos: etapas na ordem, nomes e técnica."""
    from fiep.protocolos import todos
    return {k: {"nome": p["nome"], "tecnica": p["tecnica"],
                "estagios": [{"id": e, "nome": p.get("nomes", {}).get(e, e)} for e in p["estagios"]]}
            for k, p in todos().items()}


@r.get("/amostras/{sid}")
def detalhe(sid: str, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    a = _amostra(s, sid)
    med = db.sql(s, "SELECT measurement_id, replicate_id, sensor_state, tecnica, fonte, arquivo_origem, "
                    "measurement_date, qc_planilha, qc_auto, qc_final, qc_motivos, n_pontos FROM v_medicoes "
                    "WHERE sample_id = ? ORDER BY replicate_id, sensor_state", (sid,))
    plaq = s.scalars(select(Plaqueamento).where(Plaqueamento.sample_id == sid)).all()
    pred = s.scalars(select(Predicao).where(Predicao.sample_id == sid)
                     .order_by(Predicao.previsto_em.desc(), Predicao.id.desc()).limit(40)).all()
    emp = s.get(Empresa, a.empresa_id) if a.empresa_id else None
    autor = s.get(Usuario, a.atualizado_por_id) if a.atualizado_por_id else None
    return {
        "sample_id": a.sample_id, "empresa_id": a.empresa_id, "empresa": emp.nome if emp else None,
        "coleta_id": a.coleta_id, "contamination_status": a.contamination_status,
        "sample_log10_mean_cfu_ml": a.sample_log10_mean_cfu_ml, "target_bacterium": a.target_bacterium,
        "surface_type": a.surface_type, "conjunto": a.conjunto, "observacoes": a.observacoes,
        "atualizado_em": a.atualizado_em.isoformat() if a.atualizado_em else None,
        "atualizado_por": autor.nome if autor else None,
        "medicoes": registros(med),
        "plaqueamentos": [{"replica": p.plating_replicate_id, "colonias": p.colony_count,
                           "ufc_ml": limpo(p.calculated_cfu_ml), "log10_ufc_ml": limpo(p.log10_cfu_ml)} for p in plaq],
        "previsoes": [{"previsto_em": p.previsto_em.isoformat(), "modelo_id": p.modelo_id, "replica": p.replicate_id,
                       "status": p.status, "resultado": p.resultado, "prob_contaminada": p.prob_contaminada,
                       "log10_ufc_ml_estimado": p.log10_ufc_ml_estimado, "nivel": p.nivel_contaminacao,
                       "motivo": p.motivo} for p in pred],
    }


@r.get("/amostras/{sid}/curvas")
def curvas(sid: str, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    _amostra(s, sid)
    qc = db.sql(s, "SELECT measurement_id, qc_final FROM v_medicoes WHERE sample_id = ?", (sid,))
    qc = dict(zip(qc["measurement_id"], qc["qc_final"]))
    linhas = s.execute(select(Medicao, Curva).join(Curva, Curva.measurement_id == Medicao.measurement_id)
                       .where(Medicao.sample_id == sid).order_by(Medicao.replicate_id)).all()
    return [{"measurement_id": m.measurement_id, "replicate_id": m.replicate_id, "sensor_state": m.sensor_state,
             "tecnica": m.tecnica, "qc_final": qc.get(m.measurement_id), "potential_v": c.potential_v,
             "current_ua": c.current_ua} for m, c in linhas]


@r.patch("/amostras/{sid}")
def editar(sid: str, dados: EdicaoAmostra, s: Session = Depends(sessao), u: Usuario = Depends(pode_editar)):
    a = _amostra(s, sid)
    campos = dados.model_dump(exclude_unset=True)
    if "conjunto" in campos and campos["conjunto"] not in (None, "", *CONJUNTOS):
        raise HTTPException(400, f"Conjunto inválido (use {', '.join(CONJUNTOS)} ou vazio).")
    for k, v in campos.items():
        setattr(a, k, (v.strip() or None) if isinstance(v, str) else v)
    a.atualizado_por_id = u.id
    s.commit()
    return detalhe(sid, s, u)


@r.patch("/medicoes/{mid}")
def editar_medicao(mid: str, dados: EdicaoMedicao, s: Session = Depends(sessao), _=Depends(pode_editar)):
    m = s.get(Medicao, mid)
    if m is None:
        raise HTTPException(404, "Medição não encontrada.")
    campos = dados.model_dump(exclude_unset=True)
    from fiep.protocolos import todos
    validos = [e for p in todos().values() for e in p["estagios"]]
    if campos.get("sensor_state") not in (None, *validos):
        raise HTTPException(400, f"Estágio inválido (use {', '.join(validos)}).")
    if campos.get("qc_flag") not in (None, "", "PASS", "REVIEW", "FAIL"):
        raise HTTPException(400, "qc_flag inválido (PASS, REVIEW, FAIL ou vazio).")
    for k, v in campos.items():
        setattr(m, k, v or None)
    s.commit()
    return {"ok": True}


@r.post("/amostras/{sid}/prever")
def prever_amostra(sid: str, request: Request, s: Session = Depends(sessao), u: Usuario = Depends(usuario_atual)):
    _amostra(s, sid)
    modelo = request.app.state.modelo
    pacote = modelo.pacote()
    ds = db.carregar(s, "sample_id = ?", (sid,))
    res = prever(ds, pacote, niveis=modelo.niveis())
    am = resumo_por_amostra(res)
    # guarda as réplicas e a decisão da amostra (status "amostra")
    db.gravar_predicoes(s, res, pacote["cartao"], modelo.pasta, usuario_id=u.id)
    if len(am):
        db.gravar_predicoes(s, am.assign(status="amostra", replicate_id=None, measurement_id=None,
                                         confianca=None, motivo=None), pacote["cartao"], modelo.pasta, usuario_id=u.id)
    return {"modelo": pacote["cartao"]["id"], "limiar": pacote["limiar"],
            "amostra": registros(am)[0] if len(am) else None, "replicas": registros(res)}
