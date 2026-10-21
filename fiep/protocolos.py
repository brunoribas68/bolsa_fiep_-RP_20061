"""Protocolos de biossensor: etapas (estágios) do sensor, técnica e como reconhecê-los pelo nome.

Cada protocolo tem uma ordem de etapas no MESMO eletrodo; o modelo usa a diferença entre a última
etapa e a anterior (antes e depois do contato com o alvo). A pipeline reconhece o protocolo pelos
nomes dos estágios presentes nos dados (`[dados].protocolo = "auto"`) e grava no modelo o que usou.

Para um protocolo novo, acrescente em `configs/default.toml`:

    [protocolos.meu_sensor]
    nome = "Meu sensor"
    tecnica = "DPV"
    estagios = ["etapa_a", "etapa_b", "etapa_c"]          # na ordem do protocolo
    palavras = { etapa_a = "limpo|branco", etapa_b = "sonda", etapa_c = "alvo|final" }
    nomes = { etapa_a = "Eletrodo limpo", etapa_b = "Sonda", etapa_c = "Sonda + alvo" }
"""
from __future__ import annotations

import copy
import re

import pandas as pd

PADRAO = {
    "rrna16s": {
        "nome": "Biossensor rRNA 16S (case)",
        "tecnica": "DPV",
        "estagios": ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"],
        "palavras": {
            "carbon_clean": r"limp|clean|branco|blank|carbon|carbono|bare|tratad|ativad",
            "capture_probe": r"probe|sonda|oligo|captura|ssdna",
            "capture_probe_16S_rRNA": r"rrna|16s|hibrid|target",
        },
        "nomes": {"carbon_clean": "Carbono limpo", "capture_probe": "Sonda de captura",
                  "capture_probe_16S_rRNA": "Sonda + rRNA 16S"},
    },
    "ns1": {
        "nome": "Imunossensor NS1 (SWV)",
        "tecnica": "SWV",
        "estagios": ["bloqueio", "mAb_NS1", "final"],
        "palavras": {
            "bloqueio": r"bloq|blocking|\bbsa\b",
            "mAb_NS1": r"mab|anticorpo|antibod",
            "final": r"final",
        },
        "nomes": {"bloqueio": "Bloqueio", "mAb_NS1": "mAb-NS1", "final": "Final"},
    },
}


def todos(cfg: dict | None = None) -> dict:
    """Protocolos conhecidos: os de fábrica + os da configuração (que podem substituí-los)."""
    p = copy.deepcopy(PADRAO)
    for k, v in ((cfg or {}).get("protocolos") or {}).items():
        p[k] = {**p.get(k, {}), **v}
    return p


def estagio(texto: str, cfg: dict | None = None) -> str | None:
    """Estágio indicado por um nome (de arquivo ou de procedimento). Dentro de cada protocolo, as
    etapas finais são testadas primeiro ("Oligo + rRNA" é a etapa do rRNA, não a da sonda)."""
    for prot in todos(cfg).values():
        for est in reversed(prot["estagios"]):
            rx = prot.get("palavras", {}).get(est)
            if rx and re.search(rx, texto or "", re.I):
                return est
    return None


def de_estagio(est: str, cfg: dict | None = None) -> str | None:
    return next((k for k, p in todos(cfg).items() if est in p["estagios"]), None)


def detectar(medicoes: pd.DataFrame, cfg: dict | None = None) -> str | None:
    """Protocolo com mais medições nos dados (pelos estágios presentes)."""
    if medicoes is None or "sensor_state" not in medicoes or medicoes["sensor_state"].isna().all():
        return None
    contagem = {k: int(medicoes["sensor_state"].isin(p["estagios"]).sum()) for k, p in todos(cfg).items()}
    k = max(contagem, key=contagem.get)
    return k if contagem[k] else None


def aplicar(cfg: dict, chave: str) -> dict:
    p = todos(cfg)[chave]
    novo = copy.deepcopy(cfg)
    novo["dados"].update({"protocolo": chave, "estagios": list(p["estagios"]), "tecnica": p["tecnica"]})
    novo.setdefault("features", {})["estagio_unico"] = p["estagios"][-1]
    return novo


def ajustar(cfg: dict, ds) -> dict:
    """Configuração com o protocolo dos dados (`[dados].protocolo` = "auto") ou o indicado."""
    escolhido = cfg.get("dados", {}).get("protocolo", "auto")
    chave = detectar(ds.medicoes, cfg) if escolhido in (None, "", "auto") else escolhido
    return aplicar(cfg, chave) if chave in todos(cfg) else cfg


def nomes_estagios(cfg: dict | None = None) -> dict:
    return {e: n for p in todos(cfg).values() for e, n in p.get("nomes", {}).items()}
