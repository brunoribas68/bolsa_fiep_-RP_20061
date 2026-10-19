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
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (balanced_accuracy_score, confusion_matrix, f1_score,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from . import __version__
from .features import colunas_features, tabela_features
from .ingest import Dataset
from .preprocess import curvas_por_medicao, inferir_grade, para_matriz
from .qc import aceitas, avaliar

log = logging.getLogger(__name__)


def candidatos(seed: int) -> dict:
    def pipe(clf, escalar=True):
        passos = [("imputar", SimpleImputer(strategy="median"))]
        if escalar:
            passos.append(("escalar", StandardScaler()))
        return Pipeline(passos + [("clf", clf)])
    return {
        "log_reg": pipe(LogisticRegression(max_iter=3000, class_weight="balanced", random_state=seed)),
        "random_forest": pipe(RandomForestClassifier(n_estimators=400, class_weight="balanced",
                                                     random_state=seed, n_jobs=-1), escalar=False),
        "svm_rbf": pipe(CalibratedClassifierCV(SVC(kernel="rbf", class_weight="balanced", random_state=seed),
                                               ensemble=False)),
    }


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
    curvas = curvas_por_medicao(ds.pontos, ok, cfg)
    if not curvas:
        raise ValueError("Nenhuma medição passou no controle de qualidade.")
    if grade is None:
        grade = inferir_grade(curvas, cfg)
    matriz = para_matriz(curvas, grade, cfg)
    tabela = tabela_features(matriz, ds.medicoes, cfg)
    return tabela, grade, qc


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "desconhecido"


def _impressao_dados(ds: Dataset) -> str:
    h = pd.util.hash_pandas_object(ds.pontos[["measurement_id", "potential_v", "current_ua"]], index=False)
    return hashlib.sha256(h.values.tobytes()).hexdigest()[:16]


def treinar(ds: Dataset, cfg: dict, pasta_modelos: str | Path = "modelos") -> dict:
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

    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    pasta = Path(pasta_modelos) / run_id
    pasta.mkdir(parents=True, exist_ok=True)
    cartao = {
        "id": run_id,
        "versao_pipeline": __version__,
        "commit": _git_commit(),
        "criado_em": dt.datetime.now().isoformat(timespec="seconds"),
        "modelo": melhor["modelo"],
        "limiar": float(melhor["limiar"]),
        "metricas_cv": {k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) else v)
                        for k, v in melhor.items() if k != "modelo"},
        "n_linhas": int(len(y)), "n_amostras": int(len(set(grupos))),
        "classes": {"0": int((y == 0).sum()), "1": int((y == 1).sum())},
        "n_folds": int(n_folds),
        "n_medicoes_qc": qc["qc_final"].value_counts().to_dict(),
        "impressao_dados": _impressao_dados(ds),
        "n_features": len(feats),
    }
    joblib.dump({"modelo": final, "features": feats, "grade": grade, "cfg": cfg,
                 "limiar": cartao["limiar"], "cartao": cartao}, pasta / "modelo.joblib")
    (pasta / "cartao.json").write_text(json.dumps(cartao, indent=2, ensure_ascii=False, default=str))
    metr.to_csv(pasta / "metricas_cv.csv", index=False)
    qc.to_csv(pasta / "qc_treino.csv", index=False)
    pd.DataFrame({"sample_id": grupos, "replicate_id": tabela["replicate_id"].to_numpy(), "y": y,
                  **{f"proba_{k}": v for k, v in oof.items()}}).to_csv(pasta / "previsoes_cv.csv", index=False)

    reg = Path(pasta_modelos) / "registro.csv"
    linha = pd.DataFrame([{"id": run_id, "modelo": cartao["modelo"], "commit": cartao["commit"],
                           "balanced_accuracy": cartao["metricas_cv"]["balanced_accuracy"],
                           "roc_auc": cartao["metricas_cv"]["roc_auc"], "n_amostras": cartao["n_amostras"],
                           "impressao_dados": cartao["impressao_dados"]}])
    linha.to_csv(reg, mode="a", header=not reg.exists(), index=False)
    (Path(pasta_modelos) / "ATUAL").write_text(run_id)
    _mlflow(cartao, metr, pasta)
    log.info("Modelo salvo em %s (%s, balanced_acc=%.3f)", pasta, cartao["modelo"],
             cartao["metricas_cv"]["balanced_accuracy"])
    return {"pasta": pasta, "cartao": cartao, "metricas": metr}


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
    run_id = run_id or (base / "ATUAL").read_text().strip()
    return joblib.load(base / run_id / "modelo.joblib")
