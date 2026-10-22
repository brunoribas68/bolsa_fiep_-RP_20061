"""Dados para os gráficos exploratórios (página Gráficos da plataforma e `fiep graficos`).

Dois tipos de gráfico, os que a equipe usa para mostrar os dados:

- **Linha (voltamogramas)**: curvas na grade comum de potencial, depois do QC e do mesmo
  pré-processamento do modelo. Média ± desvio por resultado do plaqueamento (em cada etapa ou na
  diferença última − penúltima etapa) e por etapa; opcionalmente as curvas individuais.
- **Dispersão**: um ponto por eletrodo (amostra × réplica) com os descritores de cada etapa
  (corrente e potencial do pico, área, amplitude, largura), as diferenças entre etapas e a carga
  (log10 UFC/mL) da amostra. Qualquer par de variáveis pode ir nos eixos.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .features import descritores
from .ingest import Dataset
from .preprocess import curvas_por_medicao, inferir_grade, para_matriz
from .protocolos import aplicar, detectar, todos
from .qc import aceitas, avaliar

CLASSES = {1: "contaminada", 0: "nao_contaminada", None: "sem_rotulo"}
NOMES_CLASSES = {"contaminada": "Contaminada", "nao_contaminada": "Não contaminada", "sem_rotulo": "Sem resultado"}
DESCRITORES = {"i_pico": ("corrente de pico", "µA"), "e_pico": ("potencial do pico", "V"),
               "amplitude": ("amplitude", "µA"), "area": ("área", "µA·V"),
               "largura_meia_altura": ("largura a meia altura", "V"), "i_min": ("corrente mínima", "µA")}
DIFERENCAS = ("i_pico", "e_pico", "area", "amplitude")
MAX_PONTOS_CURVA = 200


def _classe(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "sem_rotulo"
    return CLASSES.get(int(v), "sem_rotulo")


def _f(v):
    """float JSON-seguro (NaN/inf viram None)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return float(f"{v:.4g}") if math.isfinite(v) else None


def _lista(a) -> list:
    return [_f(v) for v in a]


def protocolos_presentes(ds: Dataset, cfg: dict) -> dict:
    """{chave: número de medições} dos protocolos que aparecem nos dados."""
    if ds.medicoes.empty or "sensor_state" not in ds.medicoes:
        return {}
    out = {k: int(ds.medicoes["sensor_state"].isin(p["estagios"]).sum()) for k, p in todos(cfg).items()}
    return {k: n for k, n in out.items() if n}


def dados(ds: Dataset, cfg: dict, protocolo: str | None = None, so_aprovadas: bool = True,
          individuais: int = 120, qc: pd.DataFrame | None = None) -> dict:
    """Tudo o que a página Gráficos precisa, em JSON.

    `qc` (measurement_id, qc_final) é o controle de qualidade já gravado no banco; sem ele, o QC é
    recalculado (mesma regra da pipeline)."""
    protos = protocolos_presentes(ds, cfg)
    base = {"protocolos": {k: {"nome": todos(cfg)[k].get("nome", k), "n_medicoes": n} for k, n in protos.items()}}
    chave = protocolo if protocolo in protos else detectar(ds.medicoes, cfg)
    if not chave:
        return {**base, "protocolo": None, "vazio": "Nenhuma medição com etapa reconhecida."}
    cfg = aplicar(cfg, chave)
    prot = todos(cfg)[chave]
    estagios, tecnica = list(prot["estagios"]), prot["tecnica"]
    nomes_est = {e: prot.get("nomes", {}).get(e, e) for e in estagios}

    med = ds.medicoes[ds.medicoes["sensor_state"].isin(estagios)].copy()
    med = med[med["tecnica"].fillna(tecnica) == tecnica]
    if qc is None:
        qc = avaliar(med, ds.pontos[ds.pontos["measurement_id"].isin(med["measurement_id"])], cfg)
    qc = qc[qc["measurement_id"].isin(med["measurement_id"])]
    ids = aceitas(qc, cfg) if so_aprovadas else set(med["measurement_id"])
    n_reprovadas = int(len(med) - len(aceitas(qc, cfg)))
    curvas = curvas_por_medicao(ds.pontos, ids, cfg)
    base.update({"protocolo": chave, "tecnica": tecnica,
                 "estagios": [{"id": e, "nome": nomes_est[e]} for e in estagios],
                 "classes": [{"id": c, "nome": n} for c, n in NOMES_CLASSES.items()],
                 "n_medicoes": int(len(med)), "n_reprovadas_qc": n_reprovadas})
    if not curvas:
        return {**base, "vazio": "Nenhuma medição passou no controle de qualidade."}
    grade = inferir_grade(curvas, cfg)
    matriz = para_matriz(curvas, grade, cfg)
    M = matriz.to_numpy(float)
    linha = {m: k for k, m in enumerate(matriz.index)}

    med = med[med["measurement_id"].isin(matriz.index)].copy()
    med["classe"] = [_classe(v) for v in med["contamination_status"]]
    # grade reduzida só para enviar (as médias são calculadas na grade inteira)
    passo = max(1, math.ceil(len(grade) / MAX_PONTOS_CURVA))
    sel = np.arange(0, len(grade), passo)

    def resumo(linhas: np.ndarray) -> dict:
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                m, d = np.nanmean(linhas, axis=0), np.nanstd(linhas, axis=0)
        return {"n": int(len(linhas)), "media": _lista(m[sel]), "desvio": _lista(d[sel])}

    medias = []                                            # por etapa × classe
    for e in estagios:
        for c in [*NOMES_CLASSES, "todas"]:
            g = med[(med["sensor_state"] == e) & ((med["classe"] == c) | (c == "todas"))]
            if len(g):
                medias.append({"estagio": e, "classe": c, **resumo(M[[linha[m] for m in g["measurement_id"]]])})

    # por eletrodo: curvas de cada etapa, diferença última − penúltima e descritores
    ult, ant = estagios[-1], estagios[-2] if len(estagios) > 1 else None
    pontos, difs, indiv = [], [], []
    x = grade.astype(float)
    for (sid, rep), g in med.groupby(["sample_id", "replicate_id"], dropna=False):
        por_est = dict(zip(g["sensor_state"], g["measurement_id"]))
        a0 = g.iloc[0]
        p = {"sample_id": None if pd.isna(sid) else str(sid), "replicate_id": None if pd.isna(rep) else str(rep),
             "classe": a0["classe"], "empresa_id": None if pd.isna(a0.get("empresa_id")) else int(a0["empresa_id"]),
             "log10_ufc_ml": _f(a0.get("sample_log10_mean_cfu_ml")),
             "etapas": [e for e in estagios if e in por_est]}
        for e, mid in por_est.items():
            for k, v in descritores(x, M[linha[mid]], e).items():
                p[k] = _f(v)
        for e in estagios[:-1]:
            for k in DIFERENCAS:
                a, b = p.get(f"{ult}_{k}"), p.get(f"{e}_{k}")
                p[f"delta_{k}_{ult}_vs_{e}"] = _f(a - b) if a is not None and b is not None else None
        if ant and ult in por_est and ant in por_est:
            difs.append((p["classe"], M[linha[por_est[ult]]] - M[linha[por_est[ant]]]))
        pontos.append(p)
        if len(indiv) < individuais * len(estagios):
            for e, mid in por_est.items():
                indiv.append({"estagio": e, "classe": p["classe"], "sample_id": p["sample_id"],
                              "replicate_id": p["replicate_id"],
                              "y": _lista(M[linha[mid]][sel])})

    diferenca = []
    for c in [*NOMES_CLASSES, "todas"]:
        linhas = [d for cl, d in difs if cl == c or c == "todas"]
        if linhas:
            diferenca.append({"classe": c, **resumo(np.vstack(linhas))})
    indiv_dif = [{"classe": c, "y": _lista(d[sel])} for c, d in difs[:individuais]]

    variaveis = []
    for e in estagios:
        for k, (nome, un) in DESCRITORES.items():
            variaveis.append({"id": f"{e}_{k}", "nome": f"{nomes_est[e]}: {nome}", "unidade": un, "grupo": nomes_est[e]})
    for e in estagios[:-1]:
        for k in DIFERENCAS:
            nome, un = DESCRITORES[k]
            variaveis.append({"id": f"delta_{k}_{ult}_vs_{e}", "nome": f"Δ {nome} ({nomes_est[ult]} − {nomes_est[e]})",
                              "unidade": un, "grupo": "Diferenças entre etapas"})
    variaveis.append({"id": "log10_ufc_ml", "nome": "Carga (log10 UFC/mL)", "unidade": "log10 UFC/mL", "grupo": "Plaqueamento"})
    # só as variáveis que têm algum valor
    variaveis = [v for v in variaveis if any(p.get(v["id"]) is not None for p in pontos)]

    # dispersão em colunas (bem menor que uma lista de objetos com as mesmas chaves)
    chaves = list(dict.fromkeys(k for p in pontos for k in p))
    colunas = {k: [p.get(k) for p in pontos] for k in chaves}
    return {**base, "potencial_v": [round(float(v), 4) for v in grade[sel]], "medias": medias, "diferenca": diferenca,
            "diferenca_nome": f"{nomes_est[ult]} − {nomes_est[ant]}" if ant else None,
            "individuais": indiv, "individuais_diferenca": indiv_dif,
            "pontos": colunas, "n_eletrodos": len(pontos), "variaveis": variaveis, "vazio": None}
