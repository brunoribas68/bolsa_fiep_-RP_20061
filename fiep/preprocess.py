"""Pré-processamento: transforma curvas de tamanhos diferentes numa matriz comum.

Passos (todos configuráveis em [preprocessamento]):
1. escolhe o scan (CV: último scan por padrão; DPV/SWV têm um só);
2. ordena por potencial e interpola numa grade comum de potencial;
3. suaviza (Savitzky-Golay);
4. remove linha de base (opcional: reta pelos extremos da curva).

A grade é definida no treino e gravada no modelo; na predição, usa-se a mesma grade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


def _escolher_scan(p: pd.DataFrame, regra) -> pd.DataFrame:
    scans = sorted(p["scan_index"].dropna().unique())
    if len(scans) <= 1:
        return p
    alvo = scans[-1] if regra == "ultimo" else int(regra)
    return p[p["scan_index"] == alvo]


def _curva(p: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    p = p.dropna(subset=["potential_v", "current_ua"])
    # potenciais repetidos (ida e volta) são promediados para obter uma função E -> I
    g = p.groupby("potential_v", sort=True)["current_ua"].mean()
    return g.index.to_numpy(float), g.to_numpy(float)


def inferir_grade(curvas: dict, cfg: dict) -> np.ndarray:
    pp = cfg["preprocessamento"]
    inicios = [e.min() for e, _ in curvas.values()]
    fins = [e.max() for e, _ in curvas.values()]
    passos = [np.median(np.diff(e)) for e, _ in curvas.values() if len(e) > 1]
    ini = pp["grade_inicio_v"] if pp["grade_inicio_v"] is not None else float(np.max(inicios))
    fim = pp["grade_fim_v"] if pp["grade_fim_v"] is not None else float(np.min(fins))
    passo = pp["grade_passo_v"] if pp["grade_passo_v"] is not None else float(np.median(passos))
    if fim <= ini:
        raise ValueError("As curvas não têm faixa de potencial em comum; defina a grade na configuração.")
    n = int(round((fim - ini) / passo)) + 1
    return np.round(np.linspace(ini, fim, n), 6)


def _suavizar(y: np.ndarray, janela: int, ordem: int) -> np.ndarray:
    janela = min(janela, len(y) if len(y) % 2 else len(y) - 1)
    if janela <= ordem + 1:
        return y
    return savgol_filter(y, window_length=janela, polyorder=ordem)


def _linha_base(x: np.ndarray, y: np.ndarray, frac: float) -> np.ndarray:
    k = max(2, int(len(x) * frac))
    idx = np.r_[0:k, len(x) - k:len(x)]
    a, b = np.polyfit(x[idx], y[idx], 1)
    return y - (a * x + b)


def curvas_por_medicao(pontos: pd.DataFrame, ids, cfg: dict) -> dict:
    regra = cfg["preprocessamento"]["scan_cv"]
    out = {}
    for mid, p in pontos[pontos["measurement_id"].isin(ids)].groupby("measurement_id"):
        e, i = _curva(_escolher_scan(p, regra))
        if len(e) >= 2:
            out[mid] = (e, i)
    return out


def para_matriz(curvas: dict, grade: np.ndarray, cfg: dict) -> pd.DataFrame:
    """Matriz (medições x pontos da grade). Fora da faixa medida fica NaN."""
    pp = cfg["preprocessamento"]
    linhas = {}
    for mid, (e, i) in curvas.items():
        y = np.interp(grade, e, i, left=np.nan, right=np.nan)
        ok = ~np.isnan(y)
        if ok.sum() >= 5:
            if pp["suavizar"]:
                y[ok] = _suavizar(y[ok], pp["janela_savgol"], pp["ordem_savgol"])
            if pp["linha_de_base"] == "linear_extremos":
                y[ok] = _linha_base(grade[ok], y[ok], pp["frac_extremos"])
        linhas[mid] = y
    return pd.DataFrame.from_dict(linhas, orient="index", columns=[f"{v:.3f}" for v in grade])
