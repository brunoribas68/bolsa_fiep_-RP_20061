"""Números do painel inicial."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from fiep import db

from ..deps import sessao, usuario_atual
from ..modelo import limpo, registros

r = APIRouter(prefix="/api", tags=["painel"])


@r.get("/painel")
def painel(request: Request, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    def n(q, p=()):
        return int(db.sql(s, q, p).iloc[0, 0] or 0)
    por_empresa = db.sql(s, """
        SELECT COALESCE(e.nome, '(sem empresa)') AS empresa,
               SUM(CASE WHEN a.contamination_status = 1 THEN 1 ELSE 0 END) AS contaminadas,
               SUM(CASE WHEN a.contamination_status = 0 THEN 1 ELSE 0 END) AS nao_contaminadas,
               SUM(CASE WHEN a.contamination_status IS NULL THEN 1 ELSE 0 END) AS sem_rotulo
        FROM amostras a LEFT JOIN empresas e ON e.id = a.empresa_id
        GROUP BY e.nome ORDER BY COUNT(*) DESC""")
    recentes = db.sql(s, """
        SELECT c.id, c.descricao, c.criado_em, c.n_amostras, e.nome AS empresa, u.nome AS criado_por
        FROM coletas c LEFT JOIN empresas e ON e.id = c.empresa_id LEFT JOIN usuarios u ON u.id = c.criado_por_id
        ORDER BY c.criado_em DESC LIMIT 6""")
    modelo = None
    try:
        c = request.app.state.modelo.pacote()["cartao"]
        mt = c.get("metricas_teste") or {}
        modelo = {"id": c["id"], "algoritmo": c.get("modelo"), "limiar": limpo(c.get("limiar")),
                  "ab_teste": limpo(mt.get("balanced_accuracy")), "auc_teste": limpo(mt.get("roc_auc")),
                  "n_amostras": c.get("n_amostras"), "criado_em": c.get("criado_em")}
    except Exception:  # noqa: BLE001
        pass
    return {
        "amostras": n("SELECT COUNT(*) FROM amostras"),
        "contaminadas": n("SELECT COUNT(*) FROM amostras WHERE contamination_status = 1"),
        "nao_contaminadas": n("SELECT COUNT(*) FROM amostras WHERE contamination_status = 0"),
        "sem_rotulo": n("SELECT COUNT(*) FROM amostras WHERE contamination_status IS NULL"),
        "medicoes": n("SELECT COUNT(*) FROM medicoes"),
        "replicas_completas": n("SELECT COUNT(*) FROM v_replicatas WHERE n_aprovadas >= 3"),
        "replicas": n("SELECT COUNT(*) FROM v_replicatas"),
        "reprovadas_qc": n("SELECT COUNT(*) FROM v_qc_atual WHERE qc_final = 'FAIL'"),
        "empresas": n("SELECT COUNT(*) FROM empresas"),
        "coletas": n("SELECT COUNT(*) FROM coletas"),
        "por_empresa": registros(por_empresa), "coletas_recentes": registros(recentes), "modelo": modelo,
    }
