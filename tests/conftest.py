"""Dados sintéticos para os testes: não dependem de nenhum arquivo real.

Gera voltamogramas DPV de 3 estágios por réplica. Nas amostras contaminadas, o pico
do último estágio cai em relação ao estágio anterior (bloqueio pela ligação do alvo),
imitando o efeito que o modelo precisa aprender.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

# bancos criados nos testes começam vazios (quem quiser o exemplo pede: dados_exemplo=True)
os.environ["FIEP_DADOS_EXEMPLO"] = "0"

ESTAGIOS = ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"]


def _curva(e, altura, centro=0.15, largura=0.05, ruido=0.02, rng=None):
    return altura * np.exp(-((e - centro) ** 2) / (2 * largura ** 2)) + 0.5 + rng.normal(0, ruido, len(e))


def gerar_case(n_amostras=24, n_rep=2, seed=0, e=None):
    rng = np.random.default_rng(seed)
    e = np.round(np.arange(-0.2, 0.4501, 0.005), 3) if e is None else e
    sinal, meta = [], []
    for s in range(n_amostras):
        cont = int(s % 3 != 0)                   # 2/3 contaminadas
        sid = f"S{s:03d}"
        for r in range(1, n_rep + 1):
            alturas = {"carbon_clean": 10.0, "capture_probe": 7.0 + rng.normal(0, 0.3)}
            alturas["capture_probe_16S_rRNA"] = alturas["capture_probe"] * (0.55 if cont else 0.95) + rng.normal(0, 0.2)
            for k, est in enumerate(ESTAGIOS):
                mid = f"{sid}_R{r}_{k}"
                cur = _curva(e, alturas[est], rng=rng)
                sinal.append(pd.DataFrame({"measurement_id": mid, "potential_V": e, "current_uA": cur}))
                meta.append({"measurement_id": mid, "sample_id": sid, "replicate_id": r, "sensor_state": est,
                             "contamination_status": cont, "qc_flag": "PASS", "sensor_lot": f"L{s % 3}",
                             "target_bacterium": "E. coli"})
    plaq = pd.DataFrame({"sample_id": [f"S{s:03d}" for s in range(n_amostras)],
                         "colony_count": [50 * int(s % 3 != 0) for s in range(n_amostras)]})
    return pd.concat(sinal, ignore_index=True), pd.DataFrame(meta), plaq


@pytest.fixture
def pasta_case(tmp_path):
    sinal, meta, plaq = gerar_case()
    sinal.to_csv(tmp_path / "sinal.csv", index=False)
    meta.to_csv(tmp_path / "metadados.csv", index=False)
    plaq.to_csv(tmp_path / "plaqueamento.csv", index=False)
    return tmp_path
