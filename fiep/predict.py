"""Predição para medições novas, usando exatamente o pré-processamento do treino.

A configuração, a grade de potencial, a lista de features e o limiar vêm do modelo
salvo. Medições reprovadas no controle de qualidade não recebem previsão: aparecem
no resultado com o motivo, para serem repetidas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ingest import Dataset, ingerir
from .model import montar_tabela
from .qc import avaliar


def prever(entrada, pacote: dict, niveis: dict | None = None) -> pd.DataFrame:
    """Previsão por réplica. `niveis` (limites de log10 UFC/mL) sobrepõe o que foi salvo com o modelo:
    os níveis são só um corte da carga estimada, então podem mudar sem re-treinar."""
    ds = entrada if isinstance(entrada, Dataset) else ingerir(entrada, cfg=pacote["cfg"])
    cfg, grade, feats = pacote["cfg"], pacote["grade"], pacote["features"]
    if niveis and niveis.get("limites_log10"):
        cfg = {**cfg, "niveis": niveis}
    qc = avaliar(ds.medicoes, ds.pontos, cfg)

    try:
        tabela, _, _ = montar_tabela(ds, cfg, grade=grade)
    except ValueError:
        tabela = pd.DataFrame()

    saida = []
    if not tabela.empty:
        X = tabela.reindex(columns=feats).astype(float)
        cobertura = X.notna().mean(axis=1)
        proba = pacote["modelo"].predict_proba(X)[:, 1]
        lim = pacote["limiar"]
        reg = pacote.get("regressor")
        carga = np.ravel(reg.predict(X)) if reg is not None else np.full(len(X), np.nan)
        for (_, linha), p, cob, lc in zip(tabela.iterrows(), proba, cobertura, carga):
            saida.append({
                "sample_id": linha.get("sample_id"), "replicate_id": linha.get("replicate_id"),
                "measurement_id": linha.get("measurement_id", np.nan),
                "status": "avaliada",
                "prob_contaminada": round(float(p), 4),
                "resultado": "CONTAMINADA" if p >= lim else "NÃO CONTAMINADA",
                "confianca": round(float(max(p, 1 - p)), 4),
                # carga estimada só faz sentido quando a amostra é classificada como contaminada
                "log10_ufc_ml_estimado": round(float(lc), 2) if (p >= lim and np.isfinite(lc)) else np.nan,
                "nivel_contaminacao": nivel(lc if p >= lim else None, cfg),
                "cobertura_grade": round(float(cob), 3),
                "motivo": "" if cob >= 0.95 else "curva não cobre toda a faixa de potencial do treino",
                "rotulo_informado": linha.get("contamination_status", np.nan),
            })
    # aprovadas no QC mas sem previsão: replicata sem todos os estágios do sensor
    if cfg["features"]["modo"] == "diferenca_estagios":
        usadas = set(map(tuple, tabela[["sample_id", "replicate_id"]].astype(str).values)) if len(tabela) else set()
        ok = ds.medicoes[ds.medicoes["measurement_id"].isin(qc.loc[qc["qc_final"].isin(cfg["qc"]["flags_aceitas"]), "measurement_id"])]
        estagios = cfg["dados"]["estagios"]
        for (sid, rep), g in ok.groupby(["sample_id", "replicate_id"], dropna=False):
            if (str(sid), str(rep)) in usadas:
                continue
            if pd.isna(sid):
                for mid, arq in zip(g["measurement_id"], g.get("arquivo_origem", g["measurement_id"])):
                    saida.append({"sample_id": np.nan, "replicate_id": np.nan, "measurement_id": mid,
                                  "status": "sem metadados", "prob_contaminada": np.nan,
                                  "resultado": "SEM PREVISÃO", "confianca": np.nan, "cobertura_grade": np.nan,
                                  "motivo": f"{arq}: sem linha na planilha de metadados (amostra e estágio desconhecidos)",
                                  "rotulo_informado": np.nan})
                continue
            todas = ds.medicoes[(ds.medicoes["sample_id"] == sid) & (ds.medicoes["replicate_id"] == rep)]
            faltam = [e + (" (reprovado no QC)" if e in set(todas["sensor_state"]) else "")
                      for e in estagios if e not in set(g["sensor_state"])]
            saida.append({"sample_id": sid, "replicate_id": rep, "measurement_id": "; ".join(g["measurement_id"]),
                          "status": "incompleta", "prob_contaminada": np.nan,
                          "resultado": "SEM PREVISÃO", "confianca": np.nan, "cobertura_grade": np.nan,
                          "motivo": "faltam os estágios: " + ", ".join(faltam) if faltam else "curvas fora da grade",
                          "rotulo_informado": np.nan})

    reprov = qc[~qc["qc_final"].isin(cfg["qc"]["flags_aceitas"])].merge(
        ds.medicoes[["measurement_id", "sample_id", "replicate_id"]], on="measurement_id", how="left")
    for _, r in reprov.iterrows():
        saida.append({"sample_id": r["sample_id"], "replicate_id": r["replicate_id"],
                      "measurement_id": r["measurement_id"], "status": f"reprovada no QC ({r['qc_final']})",
                      "prob_contaminada": np.nan, "resultado": "REPETIR MEDIÇÃO", "confianca": np.nan,
                      "cobertura_grade": np.nan,
                      "motivo": r["qc_motivos"] or f"qc_flag da planilha = {r['qc_planilha']}",
                      "rotulo_informado": np.nan})
    if not saida:
        return pd.DataFrame(columns=["sample_id", "status", "resultado", "motivo"])
    out = pd.DataFrame(saida)
    out.attrs["limiar"] = pacote["limiar"]
    out.attrs["cfg"] = cfg
    return out


# ----------------------------------------------------------------------------- níveis de contaminação

def niveis_ativos(cfg: dict) -> bool:
    n = (cfg or {}).get("niveis") or {}
    return bool(n.get("limites_log10"))


def nivel(log10_ufc, cfg: dict) -> str:
    """Nível da contaminação pela carga (log10 UFC/mL), com os limites de `[niveis]` da configuração.
    Sem limites configurados, devolve só "detectada"/"não detectada"."""
    if log10_ufc is None or (isinstance(log10_ufc, float) and not np.isfinite(log10_ufc)):
        return "não detectada" if log10_ufc is None else "detectada"
    n = (cfg or {}).get("niveis") or {}
    limites, nomes = list(n.get("limites_log10") or []), list(n.get("nomes") or [])
    if not limites:
        return "detectada"
    if len(nomes) != len(limites) + 1:
        nomes = [f"nivel_{i + 1}" for i in range(len(limites) + 1)]
    import bisect
    return nomes[bisect.bisect_right(limites, float(log10_ufc))]


def resumo_por_amostra(res: pd.DataFrame, limiar: float | None = None, cfg: dict | None = None) -> pd.DataFrame:
    """Uma linha por amostra: junta as réplicas avaliadas (média das probabilidades).

    `concordancia` é a fração das réplicas que concordam com o resultado da amostra; réplicas
    reprovadas ou incompletas aparecem na contagem, mas não entram na decisão."""
    if res.empty or "sample_id" not in res:
        return pd.DataFrame()
    limiar = res.attrs.get("limiar", 0.5) if limiar is None else limiar
    cfg = cfg if cfg is not None else res.attrs.get("cfg")
    linhas = []
    for sid, g in res.dropna(subset=["sample_id"]).groupby("sample_id", sort=True):
        av = g[g["status"] == "avaliada"]
        p = float(av["prob_contaminada"].mean()) if len(av) else np.nan
        if len(av):
            resultado = "CONTAMINADA" if p >= limiar else "NÃO CONTAMINADA"
            conc = float(((av["prob_contaminada"] >= limiar) == (p >= limiar)).mean())
        else:
            resultado = "REPETIR MEDIÇÃO" if (g["resultado"] == "REPETIR MEDIÇÃO").any() else "SEM PREVISÃO"
            conc = np.nan
        carga = av.loc[av["prob_contaminada"] >= limiar, "log10_ufc_ml_estimado"].mean() if len(av) else np.nan
        carga = float(carga) if pd.notna(carga) and resultado == "CONTAMINADA" else np.nan
        linhas.append({
            "sample_id": sid, "resultado": resultado, "prob_contaminada": round(p, 4) if len(av) else np.nan,
            "replicas_avaliadas": int(len(av)), "replicas_total": int(g["replicate_id"].nunique()),
            "concordancia": round(conc, 3) if len(av) else np.nan,
            "log10_ufc_ml_estimado": round(carga, 2) if pd.notna(carga) else np.nan,
            "nivel_contaminacao": (nivel(carga if resultado == "CONTAMINADA" else None, cfg)
                                   if resultado in ("CONTAMINADA", "NÃO CONTAMINADA") else ""),
            "rotulo_informado": g["rotulo_informado"].dropna().iloc[0] if g["rotulo_informado"].notna().any() else np.nan,
        })
    return pd.DataFrame(linhas)
