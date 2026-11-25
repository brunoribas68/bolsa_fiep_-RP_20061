"""Dados sintéticos para os testes: nenhum arquivo real (o repositório é público).

Gera voltamogramas DPV parecidos com os do genossensor: linha de base + pico perto de 0,18 V. Com o RNA,
o pico cai (sensor signal-off), mais quanto maior a concentração. Cada eletrodo tem a sua escala.

Para não depender de .nox reais, a fixture `nox_sintetico` troca o leitor de .nox por um que lê um JSON
gravado com a extensão .nox (procedimento, potencial e corrente): o resto do código roda igual.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

E = np.linspace(-0.3, 0.596, 179)


def curva(rng, rna: bool, conc: float = 1.0, escala: float = 1.0):
    altura = 7 * escala * (1 - (0.3 + 0.08 * np.log10(conc + 1)) * rna)
    i = 5 * escala + 1.5 * np.clip(-E, 0, None) + altura * np.exp(-((E - 0.18) / 0.06) ** 2)
    return E.tolist(), (i + rng.normal(0, 0.05, E.size)).tolist()


def escrever_nox(caminho: Path, procedimento: str, e, i, canal: str = "MAC80196#1") -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps({"procedimento": procedimento, "canal": canal, "e": list(e), "i": list(i)}))
    return caminho


def _ler_nox_sintetico(path):
    d = json.loads(Path(path).read_text())
    info = {"procedimento": d["procedimento"], "instrumento": d["canal"], "data_hora_procedimento": None}
    return info, [{"tecnica": "DPV", "potential_v": d["e"], "current_ua": d["i"]}]


@pytest.fixture
def nox_sintetico(monkeypatch):
    import fiep.genossensor
    monkeypatch.setattr(fiep.genossensor, "nox_to_curves", _ler_nox_sintetico)


def gerar_pasta(pasta: Path, n_eletrodos: int = 4, concs=(0.5, 5.0, 50.0), seed: int = 0) -> Path:
    """dados/rna de mentira: nao_contaminado/dpv-branco-Ej.nox e contaminado/dpv-RNA-<c>-Ej.nox."""
    rng = np.random.default_rng(seed)
    for k in range(1, n_eletrodos + 1):
        esc = rng.uniform(0.7, 1.3)
        escrever_nox(pasta / "nao_contaminado" / f"dpv-branco-E{k}.nox", "DPV SPCE H2SO4 Oligo 4N Branco",
                     *curva(rng, False, escala=esc))
        for c in concs:
            nome = f"dpv-RNA-{c:.1f}".replace(".", ",") + f"-E{k}.nox"
            escrever_nox(pasta / "contaminado" / nome, f"DPV SPCE H2SO4 Oligo 4N RNA {c:g} ng-mL",
                         *curva(rng, True, c, escala=esc))
    return pasta


@pytest.fixture
def pasta_rna(tmp_path, nox_sintetico):
    return gerar_pasta(tmp_path / "rna")
