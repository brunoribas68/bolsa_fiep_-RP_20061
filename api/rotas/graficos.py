"""Gráficos: as curvas de branco e de RNA e as medidas do pico de cada ensaio."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fiep import db, genossensor

from ..deps import sessao, usuario_atual
from ..modelo import registros

r = APIRouter(prefix="/api", tags=["graficos"])

PONTOS = ["id", "arquivo", "eletrodo_id", "tipo", "concentracao", "e_pico_v", "i_pico_ua", "i_base_ua", "altura_ua",
          "largura_v", "area_uav", "queda_pct", "abaixo_do_branco", "qc_flag"]


@r.get("/graficos")
def graficos(empresa_id: int | None = None, s: Session = Depends(sessao), _=Depends(usuario_atual)):
    """Curvas (para o gráfico de linha) e uma linha por ensaio (para a dispersão)."""
    df = genossensor.tabela(s, incluir_curvas=True, empresa_id=empresa_id)
    empresas = db.sql(s, "SELECT e.id, e.nome FROM empresas e WHERE EXISTS "
                         "(SELECT 1 FROM ensaios x WHERE x.empresa_id = e.id) ORDER BY e.nome").to_dict("records")
    if df.empty:
        return {"curvas": [], "pontos": [], "calibracao": None, "empresas": empresas}
    curvas = [{"id": int(r.id), "arquivo": r.arquivo, "eletrodo_id": r.eletrodo_id, "tipo": r.tipo,
               "concentracao": float(r.concentracao), "qc_flag": r.qc_flag if isinstance(r.qc_flag, str) else None,
               "e": [round(float(x), 4) for x in r.potential_v], "i": [round(float(x), 4) for x in r.current_ua]}
              for r in df.itertuples()]
    return {"curvas": curvas, "pontos": registros(df[PONTOS]), "calibracao": genossensor.calibracao(df),
            "empresas": empresas}
