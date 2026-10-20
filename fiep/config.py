"""Configuração da pipeline: um único lugar com todos os parâmetros.

Os valores padrão ficam em `configs/default.toml`. Treino e predição usam a MESMA
configuração (ela é gravada junto com o modelo), garantindo que o pré-processamento
aplicado a uma medição nova seja idêntico ao usado no treino.
"""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "dados": {
        # estados do sensor na ordem do protocolo (antes -> depois do contato com o alvo)
        "estagios": ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"],
        "tecnica": "DPV",
    },
    "qc": {
        "flags_aceitas": ["PASS"],          # qc_flag vindo da planilha de metadados
        "min_pontos": 50,
        "max_frac_nan": 0.02,
        "max_desvio_e_v": 0.020,            # |E medido - E aplicado| tolerado (V)
        "max_frac_desvio_e": 0.05,          # fração de pontos com desvio acima do tolerado
        "max_abs_corrente_ua": 5000.0,      # acima disso: sobrecarga provável
        "fator_outlier_lote": 10.0,         # |I| máx > fator x mediana da mesma técnica/estágio
    },
    "preprocessamento": {
        "grade_inicio_v": None,             # None = inferir da sobreposição dos dados
        "grade_fim_v": None,
        "grade_passo_v": None,
        "scan_cv": "ultimo",                # CV: qual scan usar ("ultimo" ou número)
        "suavizar": True,
        "janela_savgol": 11,
        "ordem_savgol": 3,
        "linha_de_base": "nenhuma",         # "nenhuma" ou "linear_extremos"
        "frac_extremos": 0.10,
    },
    "features": {
        "modo": "diferenca_estagios",       # "diferenca_estagios" ou "estagio_unico"
        "estagio_unico": "capture_probe_16S_rRNA",
        "curva_delta_completa": True,
    },
    # dedução automática dos metadados dos .nox (fiep/metadados_auto.py)
    "metadados": {"padrao_nome": ""},
    # proporções da divisão por amostra dos dados soltos em dados/ (ver fiep/divisao.py)
    "divisao": {"treino": 0.50, "validacao": 0.25, "teste": 0.25},
    "modelo": {
        "candidatos": ["log_reg", "random_forest", "svm_rbf"],
        "n_folds": 5,
        "seed": 42,
        "metrica": "balanced_accuracy",
    },
}


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _none(v):
    return None if v in ("", "auto", "none", "None") else v


def load_config(path: str | Path | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, "rb") as f:
            cfg = _merge(cfg, tomllib.load(f))
    p = cfg["preprocessamento"]
    for k in ("grade_inicio_v", "grade_fim_v", "grade_passo_v"):
        p[k] = _none(p[k])
    return cfg
