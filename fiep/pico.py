"""Pico de um voltamograma DPV (potencial, corrente, base, altura, largura e área) e correção da linha de base.

O pico é o máximo local de maior proeminência nos 90 % centrais da faixa de potencial: nas pontas
a corrente sobe ou desce (dupla camada, troca de sentido) e o máximo absoluto costuma cair ali.

Linha de base ("achatamento"), para o modelo comparar com a curva crua:
- `vales`: reta entre o ponto mais baixo de cada lado do pico ("vale a vale"), o jeito clássico de medir
  o pico de DPV e o mais parecido com a base linear do NOVA;
- `als`: mínimos quadrados assimétricos (Eilers & Boelens, 2005), uma curva suave que passa por baixo do
  sinal e acompanha bases curvas.
"""
from __future__ import annotations

import numpy as np

_trapz = getattr(np, "trapezoid", None) or np.trapz
CAMPOS = ("e_pico_v", "i_pico_ua", "i_base_ua", "altura_ua", "largura_v", "area_uav")


def achar_pico(e: np.ndarray, i: np.ndarray, margem: float = 0.05):
    """(índice, proeminência) do pico, ou None se a curva for curta demais."""
    from scipy.signal import find_peaks
    if len(e) < 7:
        return None
    lo, hi = np.nanmin(e), np.nanmax(e)
    miolo = (e >= lo + margem * (hi - lo)) & (e <= hi - margem * (hi - lo))
    amplitude = float(np.nanmax(i) - np.nanmin(i)) or 1.0
    idx, prop = find_peaks(i, prominence=0.02 * amplitude)
    ok = miolo[idx]
    if ok.any():
        k = int(np.argmax(np.where(ok, prop["prominences"], -np.inf)))
        return int(idx[k]), float(prop["prominences"][k])
    cand = np.where(miolo, i, -np.inf)            # sem máximo local: o maior valor do miolo
    return (int(np.argmax(cand)), 0.0) if np.isfinite(cand).any() else None


def _r(x, casas=4):
    return None if x is None or not np.isfinite(x) else round(float(x), casas)


def medir_pico(e, i) -> dict:
    """Medidas do pico (chaves de CAMPOS); vazio se não houver pico."""
    e, i = np.asarray(e, float), np.asarray(i, float)
    ok = np.isfinite(e) & np.isfinite(i)
    ordem = np.argsort(e[ok])
    e, i = e[ok][ordem], i[ok][ordem]
    achado = achar_pico(e, i)
    if achado is None:
        return {}
    k, prom = achado
    meia = i[k] - prom / 2
    esq = k
    while esq > 0 and i[esq] > meia:
        esq -= 1
    dir_ = k
    while dir_ < len(i) - 1 and i[dir_] > meia:
        dir_ += 1
    return {"e_pico_v": _r(e[k]), "i_pico_ua": _r(i[k], 3), "i_base_ua": _r(i[k] - prom, 3),
            "altura_ua": _r(prom, 3), "largura_v": _r(e[dir_] - e[esq]) if prom else None,
            "area_uav": _r(_trapz(i, e), 4)}


def linha_base(e, i, metodo: str = "vales", lam: float = 1e4, p: float = 0.01, iteracoes: int = 10) -> np.ndarray:
    """A linha de base estimada, nos mesmos pontos de `e` (que precisa estar em ordem crescente)."""
    e, i = np.asarray(e, float), np.asarray(i, float)
    if metodo == "vales":
        achado = achar_pico(e, i)
        if achado is None:
            return np.zeros_like(i)
        k = achado[0]
        m = 0.05 * (e[-1] - e[0])
        esq = np.where((e >= e[0] + m) & (e < e[k]))[0]
        dir_ = np.where((e <= e[-1] - m) & (e > e[k]))[0]
        if not len(esq) or not len(dir_):
            return np.zeros_like(i)
        a, b = esq[np.argmin(i[esq])], dir_[np.argmin(i[dir_])]
        return i[a] + (i[b] - i[a]) * (e - e[a]) / (e[b] - e[a])
    if metodo == "als":
        from scipy import sparse
        from scipy.sparse.linalg import spsolve
        n = len(i)
        D = sparse.diags([1.0, -2.0, 1.0], [0, -1, -2], shape=(n, n - 2))
        H = lam * D.dot(D.T)
        w = np.ones(n)
        z = i
        for _ in range(iteracoes):
            z = spsolve((sparse.spdiags(w, 0, n, n) + H).tocsc(), w * i)
            w = np.where(i > z, p, 1 - p)
        return z
    raise ValueError(f"linha de base desconhecida: {metodo}")
