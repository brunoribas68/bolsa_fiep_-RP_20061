"""Extração de características (features) a partir da matriz pré-processada.

Dois modos (config [features].modo):
- "diferenca_estagios": 1 linha por (sample_id, replicate_id). Usa os descritores de cada
  estágio do sensor e as DIFERENÇAS entre estágios (último - anterior), que medem o efeito
  do contato com o alvo no mesmo eletrodo. Foi a abordagem que funcionou no case.
- "estagio_unico": 1 linha por medição de um estágio escolhido (útil quando só há o
  estágio final, como em parte dos arquivos .nox reais).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_trapz = getattr(np, "trapezoid", None) or np.trapz
ID_COLS = ["sample_id", "replicate_id"]
NAO_FEATURES = {"sample_id", "replicate_id", "measurement_id", "contamination_status",
                "sample_log10_mean_cfu_ml", "sensor_lot", "target_bacterium", "experimental_batch"}


def descritores(x: np.ndarray, y: np.ndarray, prefixo: str) -> dict:
    ok = ~np.isnan(y)
    x, y = x[ok], y[ok]
    if len(y) < 3:
        return {}
    k = int(np.argmax(y))
    pico, base = y[k], np.median(y)
    meia = base + (pico - base) / 2
    acima = y >= meia
    return {
        f"{prefixo}_i_pico": float(pico),
        f"{prefixo}_e_pico": float(x[k]),
        f"{prefixo}_i_min": float(y.min()),
        f"{prefixo}_amplitude": float(pico - y.min()),
        f"{prefixo}_area": float(_trapz(y, x)),
        f"{prefixo}_largura_meia_altura": float(x[acima].max() - x[acima].min()) if acima.any() else 0.0,
    }


def _grade(matriz: pd.DataFrame) -> np.ndarray:
    return matriz.columns.astype(float).to_numpy()


def tabela_features(matriz: pd.DataFrame, medicoes: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    fcfg = cfg["features"]
    x = _grade(matriz)
    med = medicoes.set_index("measurement_id")
    rot = [c for c in ["contamination_status", "sample_log10_mean_cfu_ml", "sensor_lot",
                       "target_bacterium", "experimental_batch"] if c in med]

    if fcfg["modo"] == "estagio_unico":
        alvo = fcfg["estagio_unico"]
        linhas = []
        for mid, y in matriz.iterrows():
            if mid not in med.index:
                continue
            estado = med.at[mid, "sensor_state"]
            if alvo and pd.notna(estado) and estado != alvo:
                continue                              # outro estágio do sensor: não entra
            r = {"measurement_id": mid, "sample_id": med.at[mid, "sample_id"],
                 "replicate_id": med.at[mid, "replicate_id"]}
            r.update({c: med.at[mid, c] for c in rot})
            r.update(descritores(x, y.to_numpy(float), "s"))
            r.update({f"I_{c}": v for c, v in y.items()})
            linhas.append(r)
        return pd.DataFrame(linhas)

    estagios = cfg["dados"]["estagios"]
    ult, ant = estagios[-1], estagios[-2]
    m = med.loc[med.index.intersection(matriz.index)].rename_axis("measurement_id").reset_index()
    linhas = []
    for (sid, rep), g in m.groupby(ID_COLS, dropna=False):
        por_est = {r.sensor_state: r.measurement_id for r in g.itertuples()}
        if not all(e in por_est for e in estagios):
            continue                                  # replicata incompleta após o QC
        r = {"sample_id": sid, "replicate_id": rep}
        r.update({c: g[c].iloc[0] for c in rot})
        curvas = {e: matriz.loc[por_est[e]].to_numpy(float) for e in estagios}
        for e in estagios:
            r.update(descritores(x, curvas[e], e))
        for e in estagios[:-1]:
            for nome in ("i_pico", "area", "e_pico"):
                r[f"delta_{nome}_{ult}_vs_{e}"] = r.get(f"{ult}_{nome}", np.nan) - r.get(f"{e}_{nome}", np.nan)
        if fcfg["curva_delta_completa"]:
            delta = curvas[ult] - curvas[ant]
            r.update({f"D_{v:.3f}": d for v, d in zip(x, delta)})
        linhas.append(r)
    return pd.DataFrame(linhas)


def colunas_features(tabela: pd.DataFrame) -> list[str]:
    return [c for c in tabela.columns if c not in NAO_FEATURES]
