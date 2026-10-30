"""Picos de cada voltamograma: potencial e corrente, como se lê no gráfico do NOVA.

- DPV / SWV: o pico (máximo da corrente) com potencial, corrente, corrente de base (mediana da
  curva), altura acima da base, largura a meia altura e área.
- CV (último ciclo): pico anódico (Epa, Ipa) na varredura de ida, catódico (Epc, Ipc) na volta,
  ΔEp = Epa − Epc, E½ = (Epa + Epc)/2 e Ipa/|Ipc| — os números usados para avaliar o eletrodo com
  ferri/ferrocianeto (reversibilidade e área ativa).

Serve para mostrar os dados mesmo quando o modelo não pode classificar (ex.: só o eletrodo tratado,
ou uma técnica que o modelo não usa) e para conferir a medição.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import achar_pico as _pico

_trapz = getattr(np, "trapezoid", None) or np.trapz


def _r(x, casas=4):
    return None if x is None or not np.isfinite(x) else round(float(x), casas)


def _pulso(e: np.ndarray, i: np.ndarray) -> dict:
    ok = np.isfinite(e) & np.isfinite(i)
    ordem = np.argsort(e[ok])
    e, i = e[ok][ordem], i[ok][ordem]
    achado = _pico(e, i)
    if achado is None:
        return {}
    k, prom = achado
    meia = i[k] - prom / 2
    # largura a meia altura em volta do pico (acima da base local dada pela proeminência)
    esq = k
    while esq > 0 and i[esq] > meia:
        esq -= 1
    dir_ = k
    while dir_ < len(i) - 1 and i[dir_] > meia:
        dir_ += 1
    return {"e_pico_v": _r(e[k]), "i_pico_ua": _r(i[k], 3), "i_base_ua": _r(i[k] - prom, 3),
            "altura_ua": _r(prom, 3), "largura_v": _r(e[dir_] - e[esq]) if prom else None,
            "area_uav": _r(_trapz(i, e), 4)}


def _cv(p: pd.DataFrame) -> dict:
    n_ciclos = int(p["scan_index"].nunique()) if "scan_index" in p else 1
    if "scan_index" in p and p["scan_index"].notna().any():
        p = p[p["scan_index"] == p["scan_index"].max()]          # último ciclo (o mais estável)
    e = p["potential_v"].to_numpy(float)
    i = p["current_ua"].to_numpy(float)
    ok = np.isfinite(e) & np.isfinite(i)
    e, i = e[ok], i[ok]
    if len(e) < 10:
        return {}
    de = np.diff(e, prepend=e[0])
    if len(de) > 1:
        de[0] = de[1]
    sobe = de > 0
    if sobe.sum() < 5 or (~sobe).sum() < 5:
        return {}
    # anódico: máximo local na varredura para potenciais maiores; catódico: mínimo local na volta
    ea, ia = e[sobe], i[sobe]
    ec, ic = e[~sobe], i[~sobe]
    oa, oc = np.argsort(ea), np.argsort(ec)
    pa, pc = _pico(ea[oa], ia[oa], +1), _pico(ec[oc], ic[oc], -1)
    if pa is None or pc is None:
        return {}
    epa, ipa = ea[oa][pa[0]], ia[oa][pa[0]]
    epc, ipc = ec[oc][pc[0]], ic[oc][pc[0]]
    return {"epa_v": _r(epa), "ipa_ua": _r(ipa, 3), "epc_v": _r(epc), "ipc_ua": _r(ipc, 3),
            "delta_ep_v": _r(epa - epc), "e_meia_v": _r((epa + epc) / 2),
            "razao_ipa_ipc": _r(ipa / abs(ipc), 3) if ipc else None,
            "ciclos": n_ciclos}


def picos(medicoes: pd.DataFrame, pontos: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por medição com os picos encontrados."""
    linhas = []
    por = dict(tuple(pontos.groupby("measurement_id"))) if len(pontos) else {}
    for _, m in medicoes.iterrows():
        p = por.get(m["measurement_id"])
        base = {"measurement_id": m["measurement_id"], "sample_id": m.get("sample_id"),
                "replicate_id": m.get("replicate_id"), "sensor_state": m.get("sensor_state"),
                "tecnica": m.get("tecnica"), "arquivo": m.get("arquivo_origem")}
        if p is None or p.empty:
            linhas.append(base)
            continue
        tec = str(m.get("tecnica") or "").upper()
        if tec == "CV":
            base.update(_cv(p))
        else:
            if "scan_index" in p and p["scan_index"].nunique() > 1:
                p = p[p["scan_index"] == p["scan_index"].max()]
            base.update(_pulso(p["potential_v"].to_numpy(float), p["current_ua"].to_numpy(float)))
        linhas.append(base)
    return pd.DataFrame(linhas)
