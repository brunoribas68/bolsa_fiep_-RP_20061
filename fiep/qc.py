"""Controle de qualidade automático, aplicado igual no treino e na predição.

Cada medição recebe `qc_auto` (PASS / REVIEW / FAIL) e os motivos. O status final
(`qc_final`) é o pior entre o automático e o `qc_flag` informado na planilha.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ORDEM = {"PASS": 0, "REVIEW": 1, "FAIL": 2}


def _pior(a, b) -> str:
    a = a if a in ORDEM else "PASS"
    b = b if b in ORDEM else "PASS"
    return a if ORDEM[a] >= ORDEM[b] else b


def avaliar(medicoes: pd.DataFrame, pontos: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    q = cfg["qc"]
    linhas = []
    # arrays numpy por medição (bem mais rápido que fatiar o DataFrame a cada medição)
    pts = pontos.sort_values("measurement_id", kind="stable")
    chaves = pts["measurement_id"].to_numpy()
    cols = {c: (pts[c].to_numpy(float) if c in pts else None)
            for c in ("potential_v", "current_ua", "i_bruta_ua", "e_medido_v")}
    ini = {}
    if len(chaves):
        quebra = np.r_[0, np.flatnonzero(chaves[1:] != chaves[:-1]) + 1, len(chaves)]
        ini = {chaves[s]: (s, e) for s, e in zip(quebra[:-1], quebra[1:])}
    for mid in medicoes["measurement_id"]:
        faixa = ini.get(mid)
        motivos_fail = []
        imax = np.nan
        if faixa is None:
            motivos_fail.append("sem pontos")
        else:
            s, e = faixa
            n = e - s
            pv, cu = cols["potential_v"][s:e], cols["current_ua"][s:e]
            if n < q["min_pontos"]:
                motivos_fail.append(f"poucos pontos ({n})")
            frac_nan = float((np.isnan(pv) | np.isnan(cu)).mean())
            if frac_nan > q["max_frac_nan"]:
                motivos_fail.append(f"{frac_nan:.0%} de pontos inválidos")
            # sobrecarga: usa a corrente bruta quando existe (DPV/SWV do .nox), senão a resposta
            ib = cols["i_bruta_ua"][s:e] if cols["i_bruta_ua"] is not None else None
            cur = np.abs(ib if ib is not None and (~np.isnan(ib)).any() else cu)
            imax = float(np.nanmax(cur)) if (~np.isnan(cur)).any() else np.nan
            if imax > q["max_abs_corrente_ua"]:
                motivos_fail.append(f"corrente {imax:.0f} µA acima do limite (sobrecarga)")
            em = cols["e_medido_v"][s:e] if cols["e_medido_v"] is not None else None
            if em is not None and (~np.isnan(em)).any():
                # desconta o deslocamento constante: na SWV o potencial "forward" é o aplicado + a
                # amplitude do pulso; o que indica problema é o potencial não acompanhar o aplicado
                d = em - pv
                dev = np.abs(d - np.nanmedian(d))
                frac = float(np.mean(dev > q["max_desvio_e_v"]))     # NaN conta como dentro (como no pandas)
                if frac > q["max_frac_desvio_e"]:
                    motivos_fail.append(f"potencial medido longe do aplicado em {frac:.0%} dos pontos")
        auto = "FAIL" if motivos_fail else "PASS"
        linhas.append({"measurement_id": mid, "qc_auto": auto, "i_max_ua": imax,
                       "qc_motivos": "; ".join(motivos_fail)})
    qc = pd.DataFrame(linhas)

    # outlier dentro do lote: mesma técnica e estágio, só quando há referência suficiente
    chave = medicoes.set_index("measurement_id")[["tecnica", "sensor_state"]].astype(str)
    qc = qc.join(chave, on="measurement_id")
    for _, g in qc.groupby(["tecnica", "sensor_state"]):
        ok = g[g["qc_auto"] == "PASS"]
        if len(ok) < 3:
            continue
        mediana = ok["i_max_ua"].median()
        alto = g.index[(g["i_max_ua"] > q["fator_outlier_lote"] * mediana) & (g["qc_auto"] == "PASS")]
        qc.loc[alto, "qc_auto"] = "REVIEW"
        qc.loc[alto, "qc_motivos"] = f"corrente > {q['fator_outlier_lote']:g}x a mediana do lote"
    qc = qc.drop(columns=["tecnica", "sensor_state"])

    flag_planilha = medicoes.set_index("measurement_id")["qc_flag"]
    qc["qc_planilha"] = qc["measurement_id"].map(flag_planilha)
    qc["qc_final"] = [_pior(a, b) for a, b in zip(qc["qc_auto"], qc["qc_planilha"])]
    return qc


def aceitas(qc: pd.DataFrame, cfg: dict) -> set:
    """measurement_id aprovados para uso, segundo flags_aceitas da configuração."""
    return set(qc.loc[qc["qc_final"].isin(cfg["qc"]["flags_aceitas"]), "measurement_id"])
