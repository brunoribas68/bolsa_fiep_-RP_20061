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

BA_CONFIAVEL = 0.7      # abaixo disso (no teste), a previsão de etapa única sai como INCONCLUSIVO


def _nomes_etapas(cfg: dict) -> dict:
    from .protocolos import nomes_estagios
    return nomes_estagios(cfg)


def _etapa_unica(ds: Dataset, pacote: dict) -> dict:
    """(amostra, eletrodo) -> [(etapa, prob, limiar, BA no teste, cobertura)] com os modelos de etapa única."""
    out: dict = {}
    for e, d in (pacote.get("por_etapa") or {}).items():
        try:
            t, _, _ = montar_tabela(ds, d["cfg"], grade=d["grade"])
        except ValueError:
            continue
        if t.empty:
            continue
        X = t.reindex(columns=d["features"]).astype(float)
        cob = X.notna().mean(axis=1).to_numpy()
        p = d["modelo"].predict_proba(X)[:, 1]
        ba = (d.get("metricas") or {}).get("teste_balanced_accuracy")
        for (_, l), pi, c in zip(t.iterrows(), p, cob):
            out.setdefault((str(l["sample_id"]), str(l["replicate_id"])), []).append(
                (e, float(pi), float(d["limiar"]), ba, float(c)))
    return out


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
                "base": "etapas completas", "limiar": float(lim),
            })
    # aprovadas no QC mas sem previsão: replicata sem todos os estágios do sensor
    if cfg["features"]["modo"] == "diferenca_estagios":
        usadas = set(map(tuple, tabela[["sample_id", "replicate_id"]].astype(str).values)) if len(tabela) else set()
        ok = ds.medicoes[ds.medicoes["measurement_id"].isin(qc.loc[qc["qc_final"].isin(cfg["qc"]["flags_aceitas"]), "measurement_id"])]
        estagios = cfg["dados"]["estagios"]
        nomes = _nomes_etapas(cfg)
        unica = _etapa_unica(ds, pacote)
        tem_por_etapa = bool(pacote.get("por_etapa"))
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
            faltam = [nomes.get(e, e) + (" (reprovada no QC)" if e in set(todas["sensor_state"]) else "")
                      for e in estagios if e not in set(g["sensor_state"])]
            txt_faltam = "faltam as etapas: " + ", ".join(faltam) if faltam else "curvas fora da grade"
            parciais = unica.get((str(sid), str(rep)), [])
            if parciais:
                # plano B: modelo(s) treinado(s) só com a(s) etapa(s) que existem
                p = float(np.mean([x[1] for x in parciais]))
                lim_u = float(np.mean([x[2] for x in parciais]))
                bas = [x[3] for x in parciais if x[3] is not None]
                ba = float(np.mean(bas)) if bas else None
                cob = float(np.mean([x[4] for x in parciais]))
                etapas_txt = ", ".join(nomes.get(x[0], x[0]) for x in parciais)
                confiavel = ba is not None and ba >= BA_CONFIAVEL
                ba_txt = f"{ba:.2f}".replace(".", ",") if ba is not None else None
                aviso = (f"previsão só com a etapa {etapas_txt} ({txt_faltam}); "
                         + (f"o modelo dessa etapa teve acurácia balanceada {ba_txt} no teste"
                            if ba is not None else "o modelo dessa etapa não pôde ser testado"))
                if not confiavel:
                    aviso += (f" — abaixo de {BA_CONFIAVEL:.1f}".replace(".", ",")
                              + ": essa etapa sozinha não separa contaminada de não contaminada; "
                                "resultado inconclusivo, meça as outras etapas")
                if cob < 0.95:
                    aviso += "; a curva não cobre toda a faixa de potencial do treino"
                saida.append({"sample_id": sid, "replicate_id": rep, "measurement_id": "; ".join(g["measurement_id"]),
                              "status": "avaliada" if confiavel else "inconclusiva", "prob_contaminada": round(p, 4),
                              "resultado": ("CONTAMINADA" if p >= lim_u else "NÃO CONTAMINADA") if confiavel
                              else "INCONCLUSIVO",
                              "confianca": round(max(p, 1 - p), 4), "log10_ufc_ml_estimado": np.nan,
                              "nivel_contaminacao": nivel(np.nan if p >= lim_u else None, cfg),
                              "cobertura_grade": round(cob, 3), "motivo": aviso, "rotulo_informado": np.nan,
                              "base": f"etapa única ({etapas_txt})", "limiar": lim_u,
                              "ba_teste_base": ba})
                continue
            if not tem_por_etapa:
                txt_faltam += (" — o modelo em uso não tem modelos de etapa única; treine de novo "
                               "(Modelos → Treinar modelos) para prever com uma etapa só")
            saida.append({"sample_id": sid, "replicate_id": rep, "measurement_id": "; ".join(g["measurement_id"]),
                          "status": "incompleta", "prob_contaminada": np.nan,
                          "resultado": "SEM PREVISÃO", "confianca": np.nan, "cobertura_grade": np.nan,
                          "motivo": txt_faltam, "rotulo_informado": np.nan})

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
        base = "etapas completas"
        if "base" in av and len(av):
            completas = av[av["base"] == "etapas completas"]
            if len(completas):            # eletrodos com todas as etapas valem mais: usa só eles
                av = completas
            else:
                base = "etapa única"
        lim = float(av["limiar"].mean()) if "limiar" in av and av["limiar"].notna().any() else limiar
        p = float(av["prob_contaminada"].mean()) if len(av) else np.nan
        if len(av):
            resultado = "CONTAMINADA" if p >= lim else "NÃO CONTAMINADA"
            conc = float(((av["prob_contaminada"] >= lim) == (p >= lim)).mean())
        else:
            resultado = ("REPETIR MEDIÇÃO" if (g["resultado"] == "REPETIR MEDIÇÃO").any()
                         else "INCONCLUSIVO" if (g["resultado"] == "INCONCLUSIVO").any() else "SEM PREVISÃO")
            conc = np.nan
            if resultado == "INCONCLUSIVO":
                base = "etapa única"
        carga = av.loc[av["prob_contaminada"] >= lim, "log10_ufc_ml_estimado"].mean() if len(av) else np.nan
        carga = float(carga) if pd.notna(carga) and resultado == "CONTAMINADA" else np.nan
        linhas.append({
            "sample_id": sid, "resultado": resultado, "prob_contaminada": round(p, 4) if len(av) else np.nan,
            "replicas_avaliadas": int(len(av)), "replicas_total": int(g["replicate_id"].nunique()),
            "concordancia": round(conc, 3) if len(av) else np.nan,
            "log10_ufc_ml_estimado": round(carga, 2) if pd.notna(carga) else np.nan,
            "nivel_contaminacao": (nivel(carga if resultado == "CONTAMINADA" else None, cfg)
                                   if resultado in ("CONTAMINADA", "NÃO CONTAMINADA") else ""),
            "rotulo_informado": g["rotulo_informado"].dropna().iloc[0] if g["rotulo_informado"].notna().any() else np.nan,
            "base": base if len(av) or resultado == "INCONCLUSIVO" else "",
        })
    return pd.DataFrame(linhas)
