"""Gera (ou completa) a planilha de metadados de um lote de arquivos .nox.

    fiep planilha --entrada dados/treino

Cria `metadados_nox.csv` na pasta, com uma linha por .nox encontrado (inclusive em subpastas).
Se a planilha já existir, acrescenta só os arquivos que ainda não estão nela, sem mexer no que
já foi preenchido. Técnica, número de pontos e o resultado do controle de qualidade já vêm
preenchidos; o estágio do sensor é sugerido pelo nome do arquivo quando possível.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .config import load_config
from .io.nox import nox_to_curves

COLUNAS = [
    "arquivo", "measurement_id", "sample_id", "replicate_id", "sensor_state", "contamination_status",
    "sample_log10_mean_cfu_ml", "qc_flag", "target_bacterium", "surface_type", "sensor_lot",
    "experimental_batch", "operator_id", "measurement_date",
    # preenchidas automaticamente, só para conferência
    "tecnica", "n_pontos", "qc_automatico", "observacoes",
]

_ESTAGIOS = [
    (re.compile(r"rrna|16s|alvo|target", re.I), "capture_probe_16S_rRNA"),
    (re.compile(r"probe|sonda|oligo|captura", re.I), "capture_probe"),
    (re.compile(r"limp|clean|branco|blank|carbon|bare", re.I), "carbon_clean"),
]


def sugerir_estagio(nome: str) -> str | None:
    for rx, est in _ESTAGIOS:
        if rx.search(nome):
            return est
    return None


def _qc_rapido(curva: dict, cfg: dict) -> str:
    q = cfg["qc"]
    motivos = []
    ib = curva.get("i_bruta_ua") or curva["current_ua"]
    imax = max(abs(v) for v in ib if v == v) if ib else 0
    if imax > q["max_abs_corrente_ua"]:
        motivos.append(f"sobrecarga ({imax:.0f} µA)")
    em = curva.get("e_medido_v")
    if em:
        dev = [abs(a - b) > q["max_desvio_e_v"] for a, b in zip(curva["potential_v"], em) if b == b]
        if dev and sum(dev) / len(dev) > q["max_frac_desvio_e"]:
            motivos.append("potencial medido longe do aplicado")
    if len(curva["potential_v"]) < q["min_pontos"]:
        motivos.append("poucos pontos")
    return "FAIL: " + "; ".join(motivos) if motivos else "PASS"


def gerar_planilha(pasta: str | Path, nome: str = "metadados_nox.csv", cfg: dict | None = None) -> tuple[Path, int]:
    """Cria/atualiza a planilha. Devolve (caminho, nº de linhas novas)."""
    pasta = Path(pasta)
    cfg = cfg or load_config()
    destino = pasta / nome
    existente = pd.read_csv(destino, dtype=str, sep=None, engine="python", encoding="utf-8-sig") \
        if destino.exists() else pd.DataFrame(columns=COLUNAS)
    ja = set(existente.get("arquivo", pd.Series(dtype=str)).astype(str))

    novas = []
    for arq in sorted(pasta.rglob("*.nox")):
        rel = arq.relative_to(pasta).as_posix()
        if rel in ja or arq.name in ja:
            continue
        linha = {c: "" for c in COLUNAS}
        linha.update({"arquivo": rel, "measurement_id": arq.stem})
        try:
            _, curvas = nox_to_curves(arq)
        except Exception as e:  # noqa: BLE001
            linha["observacoes"] = f"não foi possível ler: {e}"
            novas.append(linha)
            continue
        if not curvas:
            linha["observacoes"] = "sem curva de potencial x corrente"
            novas.append(linha)
            continue
        c = curvas[0]
        linha.update({"tecnica": c["tecnica"], "n_pontos": len(c["potential_v"]), "qc_automatico": _qc_rapido(c, cfg)})
        est = sugerir_estagio(arq.stem)
        if est:
            linha["sensor_state"] = est
            linha["observacoes"] = "sensor_state sugerido pelo nome do arquivo: confira"
        novas.append(linha)

    tabela = pd.concat([existente, pd.DataFrame(novas, columns=COLUNAS)], ignore_index=True)
    # utf-8-sig: o Excel em português abre com acentos corretos
    tabela.to_csv(destino, index=False, encoding="utf-8-sig")
    return destino, len(novas)
