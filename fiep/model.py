"""Treino, avaliação e registro de modelos.

- Validação cruzada AGRUPADA por amostra (StratifiedGroupKFold): réplicas e estágios
  da mesma amostra nunca ficam em treino e teste ao mesmo tempo.
- O limiar de decisão é escolhido nas previsões fora da dobra (índice J de Youden).
- Cada treino gera uma pasta em `modelos/<id>/` com o modelo, a configuração usada,
  a grade de potencial, as métricas e a lista de features (o "cartão do modelo"), e
  uma linha em `modelos/registro.csv`. `modelos/ATUAL` aponta para o último treino.
- Se o MLflow estiver instalado, o treino também é registrado nele.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import subprocess
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (balanced_accuracy_score, confusion_matrix, f1_score,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import StratifiedGroupKFold

from . import __version__
from .features import colunas_features, tabela_features
from .ingest import Dataset
from .preprocess import curvas_por_medicao, inferir_grade, para_matriz
from .qc import aceitas, avaliar

log = logging.getLogger(__name__)


def candidatos(seed: int) -> dict:
    """Catálogo de classificadores (nome -> estimador não treinado). Ver também fiep.experimentos."""
    from .catalogo import classificadores
    return classificadores(seed)


def _metricas(y, proba, limiar=0.5) -> dict:
    pred = (proba >= limiar).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "sensibilidade": tp / (tp + fn) if tp + fn else np.nan,
        "especificidade": tn / (tn + fp) if tn + fp else np.nan,
        "f1": f1_score(y, pred, zero_division=0),
        "roc_auc": roc_auc_score(y, proba) if len(set(y)) > 1 else np.nan,
        "vp": int(tp), "fp": int(fp), "vn": int(tn), "fn": int(fn),
    }


def limiar_youden(y, proba) -> float:
    fpr, tpr, thr = roc_curve(y, proba)
    return float(np.clip(thr[np.argmax(tpr - fpr)], 0.0, 1.0))


def montar_tabela(ds: Dataset, cfg: dict, grade: np.ndarray | None = None):
    """QC -> curvas -> matriz na grade -> features. Retorna (tabela, grade, qc)."""
    qc = avaliar(ds.medicoes, ds.pontos, cfg)
    ok = aceitas(qc, cfg)
    tecnica = cfg["dados"].get("tecnica")
    if tecnica:                      # não mistura técnicas (ex.: um CV na mesma pasta dos DPV)
        ok &= set(ds.medicoes.loc[ds.medicoes["tecnica"].fillna(tecnica) == tecnica, "measurement_id"])
    curvas = curvas_por_medicao(ds.pontos, ok, cfg)
    if not curvas:
        raise ValueError(f"Nenhuma medição {tecnica or ''} passou no controle de qualidade.".replace("  ", " "))
    if grade is None:
        grade = inferir_grade(curvas, cfg)
    matriz = para_matriz(curvas, grade, cfg)
    tabela = tabela_features(matriz, ds.medicoes, cfg)
    return tabela, grade, qc


def _git_commit() -> str:
    """Commit do código; '+modificado' quando há alterações não commitadas no pacote."""
    raiz = Path(__file__).resolve().parents[1]
    try:
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                           check=True, cwd=raiz).stdout.strip()
        sujo = subprocess.run(["git", "status", "--porcelain", "--", "fiep", "configs"], capture_output=True,
                              text=True, cwd=raiz).stdout.strip()
        return h + ("+modificado" if sujo else "")
    except Exception:  # noqa: BLE001
        return "desconhecido"


def _impressao_dados(ds: Dataset) -> str:
    h = pd.util.hash_pandas_object(ds.pontos[["measurement_id", "potential_v", "current_ua"]], index=False)
    return hashlib.sha256(h.values.tobytes()).hexdigest()[:16]


def treinar(ds: Dataset, cfg: dict, pasta_modelos: str | Path = "modelos") -> dict:
    from .protocolos import ajustar
    cfg = ajustar(cfg, ds)
    tabela, grade, qc = montar_tabela(ds, cfg)
    tabela = tabela.dropna(subset=["contamination_status"])
    if tabela.empty:
        raise ValueError("Nenhuma linha com rótulo (contamination_status) após QC e montagem das features.")
    feats = colunas_features(tabela)
    X = tabela[feats].astype(float)
    y = tabela["contamination_status"].astype(int).to_numpy()
    grupos = tabela["sample_id"].astype(str).to_numpy()
    mcfg = cfg["modelo"]
    n_folds = min(mcfg["n_folds"], len(set(grupos)), int(np.bincount(y).min()))
    if n_folds < 2 or len(set(y)) < 2:
        raise ValueError(f"Dados insuficientes para validação cruzada (classes={np.bincount(y).tolist()}).")
    cv = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=mcfg["seed"])
    modelos = candidatos(mcfg["seed"])

    resultados, oof = [], {}
    for nome in mcfg["candidatos"]:
        proba = np.full(len(y), np.nan)
        for tr, te in cv.split(X, y, grupos):
            m = modelos[nome]
            m.fit(X.iloc[tr], y[tr])
            proba[te] = m.predict_proba(X.iloc[te])[:, 1]
        oof[nome] = proba
        lim = limiar_youden(y, proba)
        r = {"modelo": nome, "limiar": lim, **{f"{k}": v for k, v in _metricas(y, proba, lim).items()}}
        r["balanced_accuracy_limiar_0.5"] = _metricas(y, proba, 0.5)["balanced_accuracy"]
        resultados.append(r)
        log.info("CV %-14s balanced_acc=%.3f auc=%.3f", nome, r["balanced_accuracy"], r["roc_auc"])
    metr = pd.DataFrame(resultados).sort_values(mcfg["metrica"], ascending=False)
    melhor = metr.iloc[0]

    final = candidatos(mcfg["seed"])[melhor["modelo"]]
    final.fit(X, y)

    pasta, cartao = salvar_pacote(
        final, feats, grade, cfg, float(melhor["limiar"]), melhor["modelo"],
        metricas_cv={k: v for k, v in melhor.items() if k != "modelo"},
        info={"n_linhas": int(len(y)), "n_amostras": int(len(set(grupos))),
              "classes": {"0": int((y == 0).sum()), "1": int((y == 1).sum())}, "n_folds": int(n_folds),
              "n_medicoes_qc": qc["qc_final"].value_counts().to_dict(), "impressao_dados": _impressao_dados(ds)},
        pasta_modelos=pasta_modelos)
    metr.to_csv(pasta / "metricas_cv.csv", index=False)
    qc.to_csv(pasta / "qc_treino.csv", index=False)
    pd.DataFrame({"sample_id": grupos, "replicate_id": tabela["replicate_id"].to_numpy(), "y": y,
                  **{f"proba_{k}": v for k, v in oof.items()}}).to_csv(pasta / "previsoes_cv.csv", index=False)
    _mlflow(cartao, metr, pasta)
    log.info("Modelo salvo em %s (%s, balanced_acc=%.3f)", pasta, cartao["modelo"],
             cartao["metricas_cv"]["balanced_accuracy"])
    return {"pasta": pasta, "cartao": cartao, "metricas": metr}


def _num(v):
    return float(v) if isinstance(v, (int, float, np.floating, np.integer)) and not isinstance(v, bool) else v


def salvar_pacote(modelo, feats, grade, cfg, limiar, nome_modelo, metricas_cv, info,
                  pasta_modelos="modelos", extras: dict | None = None, adicionais: dict | None = None,
                  ativar: bool = True):
    """Grava modelo + grade + config + features + limiar em modelos/<id>/ e atualiza o registro.
    `ativar=True` faz dele o modelo em uso (modelos/ATUAL)."""
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(pasta_modelos)
    pasta = base / run_id
    k = 1
    while pasta.exists():                      # dois treinos no mesmo segundo
        k += 1
        pasta = base / f"{run_id}-{k}"
    pasta.mkdir(parents=True)
    cartao = {
        "id": pasta.name,
        "versao_pipeline": __version__,
        "commit": _git_commit(),
        "criado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"),   # com fuso horário
        "modelo": nome_modelo,
        "limiar": float(limiar),
        "metricas_cv": {k: _num(v) for k, v in metricas_cv.items()},
        "n_features": len(feats),
        **info,
        **(extras or {}),
    }
    joblib.dump({"modelo": modelo, "features": feats, "grade": grade, "cfg": cfg,
                 "limiar": cartao["limiar"], "cartao": cartao, **(adicionais or {})}, pasta / "modelo.joblib")
    (pasta / "cartao.json").write_text(json.dumps(cartao, indent=2, ensure_ascii=False, default=str),
                                       encoding="utf-8")
    reg = base / "registro.csv"
    pd.DataFrame([{"id": cartao["id"], "modelo": nome_modelo, "commit": cartao["commit"],
                   "balanced_accuracy": cartao["metricas_cv"].get("balanced_accuracy"),
                   "roc_auc": cartao["metricas_cv"].get("roc_auc"), "n_amostras": cartao.get("n_amostras"),
                   "impressao_dados": cartao.get("impressao_dados")}]).to_csv(
        reg, mode="a", header=not reg.exists(), index=False)
    if ativar:
        (base / "ATUAL").write_text(cartao["id"])
    return pasta, cartao


def _mlflow(cartao: dict, metr: pd.DataFrame, pasta: Path) -> None:
    try:
        import mlflow
    except ImportError:
        return
    with mlflow.start_run(run_name=cartao["id"]):
        mlflow.log_params({"modelo": cartao["modelo"], "commit": cartao["commit"],
                           "impressao_dados": cartao["impressao_dados"]})
        mlflow.log_metrics({k: v for k, v in cartao["metricas_cv"].items()
                            if isinstance(v, float) and np.isfinite(v)})
        mlflow.log_artifacts(str(pasta))


def carregar(pasta_modelos: str | Path = "modelos", run_id: str | None = None) -> dict:
    base = Path(pasta_modelos)
    if base.is_file():
        return joblib.load(base)
    if (base / "modelo.joblib").exists():
        return joblib.load(base / "modelo.joblib")
    if run_id is None and not (base / "ATUAL").exists():
        raise FileNotFoundError(f"Nenhum modelo treinado em '{base}': rode `fiep experimento` "
                                "(ou indique a pasta de um modelo com --modelo).")
    run_id = run_id or (base / "ATUAL").read_text().strip()
    return joblib.load(base / run_id / "modelo.joblib")
