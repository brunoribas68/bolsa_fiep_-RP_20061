"""Gráficos exploratórios: voltamogramas médios (linha) e descritores por eletrodo (dispersão)."""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from fiep import db
from fiep.config import load_config
from fiep.graficos import dados

from ..deps import sessao, usuario_atual

r = APIRouter(prefix="/api", tags=["graficos"])

_CACHE: OrderedDict = OrderedDict()
_TRAVA = threading.Lock()


def _versao_dados(s: Session) -> str:
    """Impressão digital do que entra nos gráficos: muda quando entra/sai medição ou muda rótulo, carga,
    etapa, réplica ou QC manual."""
    df = db.sql(s, """SELECT m.measurement_id, m.sample_id, m.replicate_id, m.sensor_state, m.tecnica, m.qc_flag,
                             a.contamination_status, a.sample_log10_mean_cfu_ml, a.empresa_id, c.n_pontos
                      FROM medicoes m LEFT JOIN amostras a ON a.sample_id = m.sample_id
                      LEFT JOIN curvas c ON c.measurement_id = m.measurement_id""")
    if df.empty:
        return "vazio"
    return hashlib.sha1(pd.util.hash_pandas_object(df.astype(str), index=False).values.tobytes()).hexdigest()


@r.get("/graficos")
def graficos(request: Request, empresa_id: int | None = None, protocolo: str | None = None,
             qc: str = Query("aprovadas", pattern="^(aprovadas|todas)$"),
             s: Session = Depends(sessao), _=Depends(usuario_atual)):
    chave = (_versao_dados(s), empresa_id, protocolo, qc)
    with _TRAVA:
        out = _CACHE.get(chave)
    if out is None:
        ds = db.carregar(s, "empresa_id = ?", (empresa_id,)) if empresa_id else db.carregar(s)
        cfg = load_config(request.app.state.config.config_pipeline)
        out = dados(ds, cfg, protocolo=protocolo, so_aprovadas=qc == "aprovadas")
        with _TRAVA:
            _CACHE[chave] = out
            while len(_CACHE) > 12:
                _CACHE.popitem(last=False)
    empresas = db.sql(s, "SELECT e.id, e.nome FROM empresas e WHERE EXISTS "
                         "(SELECT 1 FROM amostras a WHERE a.empresa_id = e.id) ORDER BY e.nome").to_dict("records")
    return {**out, "empresas": empresas}
