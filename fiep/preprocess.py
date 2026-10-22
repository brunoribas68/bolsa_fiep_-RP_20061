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
    e = p["potential_v"].to_numpy(float)
    i = p["current_ua"].to_numpy(float)
    ok = ~(np.isnan(e) | np.isnan(i))
    e, i = e[ok], i[ok]
    # potenciais repetidos (ida e volta) são promediados para obter uma função E -> I
    u, inv = np.unique(e, return_inverse=True)
    soma = np.bincount(inv, weights=i, minlength=len(u))
    n = np.bincount(inv, minlength=len(u))
    return u, soma / np.maximum(n, 1)


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
    ids = list(curvas)
    Y = np.vstack([np.interp(grade, *curvas[m], left=np.nan, right=np.nan) for m in ids]) if ids \
        else np.empty((0, len(grade)))
    # curvas com a mesma faixa válida são processadas juntas (mesmo resultado, bem mais rápido)
    mascaras = ~np.isnan(Y)
    grupos: dict[bytes, list[int]] = {}
    for k, ok in enumerate(mascaras):
        if ok.sum() >= 5:
            grupos.setdefault(ok.tobytes(), []).append(k)
    for linhas_g in grupos.values():
        ok = mascaras[linhas_g[0]]
        bloco = Y[np.ix_(linhas_g, np.flatnonzero(ok))]
        if pp["suavizar"]:
            janela = min(pp["janela_savgol"], bloco.shape[1] if bloco.shape[1] % 2 else bloco.shape[1] - 1)
            if janela > pp["ordem_savgol"] + 1:
                bloco = savgol_filter(bloco, window_length=janela, polyorder=pp["ordem_savgol"], axis=1)
        if pp["linha_de_base"] == "linear_extremos":
            bloco = np.vstack([_linha_base(grade[ok], b, pp["frac_extremos"]) for b in bloco])
        Y[np.ix_(linhas_g, np.flatnonzero(ok))] = bloco
    return pd.DataFrame(Y, index=ids, columns=[f"{v:.3f}" for v in grade])
