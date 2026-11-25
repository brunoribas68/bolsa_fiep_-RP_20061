"""Números do painel inicial."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from fiep import db

from ..deps import sessao, usuario_atual
from ..modelo import registros

r = APIRouter(prefix="/api", tags=["painel"])


@r.get("/painel")
def painel(request: Request, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    def n(q):
        return int(db.sql(s, q).iloc[0, 0] or 0)
    por_concentracao = db.sql(s, """SELECT tipo, concentracao, COUNT(*) AS ensaios, COUNT(DISTINCT eletrodo_id) AS eletrodos
                                    FROM ensaios GROUP BY tipo, concentracao ORDER BY concentracao""")
    recentes = db.sql(s, """
        SELECT c.id, c.descricao, c.criado_em, c.n_ensaios, e.nome AS empresa, u.nome AS criado_por
        FROM coletas c LEFT JOIN empresas e ON e.id = c.empresa_id LEFT JOIN usuarios u ON u.id = c.criado_por_id
        ORDER BY c.criado_em DESC LIMIT 6""")
    modelo = None
    try:
        c = request.app.state.modelo.pacote()["cartao"]
        modelo = {k: c.get(k) for k in ("id", "algoritmo", "algoritmo_nome", "representacao", "representacao_nome",
                                        "ab_referencia", "referencia", "confiavel", "criado_em")}
        modelo["n_ensaios"] = c["dados"]["n_ensaios"]
    except Exception:  # noqa: BLE001
        pass
    return {
        "branco": n("SELECT COUNT(*) FROM ensaios WHERE tipo = 'branco'"),
        "rna": n("SELECT COUNT(*) FROM ensaios WHERE tipo = 'rna'"),
        "eletrodos": n("SELECT COUNT(DISTINCT eletrodo_id) FROM ensaios"),
        "reprovados": n("SELECT COUNT(*) FROM ensaios WHERE qc_flag = 'FAIL'"),
        "empresas": n("SELECT COUNT(*) FROM empresas"),
        "coletas": n("SELECT COUNT(*) FROM coletas"),
        "por_concentracao": registros(por_concentracao), "coletas_recentes": registros(recentes), "modelo": modelo,
        "min_por_classe": 3,
    }
