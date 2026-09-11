"""
ingest_pipeline.py
===================

Etapa 2 do pipeline: "ingerir" os dados já arrumados pelo data_preparation.py.

Lê prepared_measurements.csv (+ prepared_samples.csv, opcional) e:
1. Valida qualidade (qc_flag, duplicidade, ausências).
2. Monta a tabela wide (1 linha por medição, 1 coluna por potencial).
3. Deriva features extras (pico, mínimo, amplitude de corrente).
4. Treina/valida 3 modelos (Regressão Logística, LDA, Random Forest) usando
   contamination_status como alvo, com split e CV agrupados por sample_id
   (garante que réplicas da mesma amostra não vazam entre treino/teste).
5. Exporta tudo (CSV + SQLite), igual ao pipeline original.

Uso:
    python src/ingest_pipeline.py --prepared-dir prepared --output-dir outputs
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("ingest_pipeline")

MIN_ROWS_FOR_MODELING = 8


def load_prepared(prepared_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    prepared_path = Path(prepared_dir)
    measurements_file = prepared_path / "prepared_measurements.csv"
    if not measurements_file.exists():
        raise FileNotFoundError(
            f"'{measurements_file}' não encontrado. Rode antes: "
            f"python src/data_preparation.py --input-dir <bruto> --output-dir {prepared_path}"
        )
    measurements = pd.read_csv(measurements_file)

    samples_file = prepared_path / "prepared_samples.csv"
    samples = pd.read_csv(samples_file) if samples_file.exists() else None
    return measurements, samples


def filter_by_quality(measurements: pd.DataFrame, keep_flags: tuple[str, ...] = ("PASS",)) -> pd.DataFrame:
    if "qc_flag" not in measurements.columns or measurements["qc_flag"].isna().all():
        return measurements
    before = measurements["measurement_id"].nunique()
    filtered = measurements[measurements["qc_flag"].isin(keep_flags)].copy()
    after = filtered["measurement_id"].nunique()
    if after < before:
        logger.info(
            "Filtro de qualidade (qc_flag in %s): %d -> %d medições mantidas (%d descartadas).",
            keep_flags, before, after, before - after,
        )
    return filtered


def build_wide_table(measurements: pd.DataFrame) -> pd.DataFrame:
    required = {"measurement_id", "potential_v", "current_ua", "contamination_status"}
    missing = required - set(measurements.columns)
    if missing:
        raise ValueError(f"prepared_measurements.csv não tem as colunas necessárias: {missing}")

    index_cols = [
        c
        for c in [
            "measurement_id", "sample_id", "replicate_id", "sensor_state",
            "sensor_state_code", "target_bacterium", "contamination_status", "qc_flag",
        ]
        if c in measurements.columns
    ]

    # pivot_table com dropna=False + índice multi-coluna contendo NaN pode explodir em memória
    # (o pandas monta um produto cartesiano das combinações de índice). Para evitar isso,
    # trocamos NaN por sentinelas antes do pivot e devolvemos NaN depois.
    sentinel = "__NA__"
    to_pivot = measurements.copy()
    for col in index_cols:
        if to_pivot[col].isna().any():
            to_pivot[col] = to_pivot[col].astype(object).where(to_pivot[col].notna(), sentinel)

    wide = (
        to_pivot.pivot_table(
            index=index_cols,
            columns="potential_v",
            values="current_ua",
            aggfunc="mean",
        )
        .sort_index(axis=1)
        .reset_index()
    )
    for col in index_cols:
        if wide[col].astype(object).eq(sentinel).any():
            wide[col] = wide[col].replace(sentinel, np.nan)
    wide.columns = [c if not isinstance(c, float) else f"I_{c:.6f}" for c in wide.columns]
    return wide


def prepare_features(wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    feature_cols = [c for c in wide.columns if c.startswith("I_")]
    if not feature_cols:
        raise ValueError("Nenhuma feature de corrente (I_*) encontrada na tabela wide.")
    if "contamination_status" not in wide.columns:
        raise ValueError("Coluna 'contamination_status' ausente - necessária como alvo de classificação.")
    if "sample_id" not in wide.columns:
        raise ValueError("Coluna 'sample_id' ausente - necessária para agrupar treino/teste sem vazamento.")

    df = wide.dropna(subset=["contamination_status"]).copy()
    if df.empty:
        raise ValueError("Nenhuma medição com contamination_status preenchido - não é possível treinar.")

    df["peak_current"] = df[feature_cols].max(axis=1)
    df["min_current"] = df[feature_cols].min(axis=1)
    df["delta_current"] = df["peak_current"] - df["min_current"]

    x = df[feature_cols + ["peak_current", "min_current", "delta_current"]].fillna(0.0)
    y = df["contamination_status"].astype(int)
    groups = df["sample_id"]
    return x, y, groups


def _specificity(y_true: pd.Series, y_pred: np.ndarray) -> float:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    if cm.shape != (2, 2):
        return float("nan")
    tn, fp, _, _ = cm.ravel()
    return tn / (tn + fp) if (tn + fp) else float("nan")


def train_and_evaluate(wide: pd.DataFrame, random_state: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    x, y, groups = prepare_features(wide)

    if y.nunique() < 2:
        raise ValueError(
            "contamination_status só tem uma classe nos dados fornecidos - "
            "impossível treinar um classificador binário."
        )

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    train_idx, test_idx = next(splitter.split(x, y, groups=groups))

    x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    g_train = groups.iloc[train_idx]

    n_groups = max(2, min(5, g_train.nunique()))
    cv = GroupKFold(n_splits=n_groups)
    can_cross_validate = y_train.nunique() > 1

    models: dict[str, Any] = {
        "baseline_log_reg": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state)),
            ]
        ),
        "lda": Pipeline([("scaler", StandardScaler()), ("clf", LinearDiscriminantAnalysis())]),
        "random_forest": RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=random_state, min_samples_leaf=1,
        ),
    }

    metrics_rows: list[dict[str, Any]] = []
    predictions_rows: list[pd.DataFrame] = []

    for model_name, model in models.items():
        scoring = {
            "balanced_accuracy": "balanced_accuracy",
            "f1": "f1",
            "precision": "precision",
            "recall": "recall",
        }
        if can_cross_validate:
            try:
                cv_result = cross_validate(
                    model, x_train, y_train, groups=g_train, cv=cv, scoring=scoring, error_score="raise",
                )
            except ValueError as exc:
                logger.warning(
                    "Validação cruzada falhou para '%s' (provável dobra com uma única classe, "
                    "comum com poucas amostras): %s. Métricas de CV para este modelo ficarão como NaN.",
                    model_name, exc,
                )
                cv_result = {f"test_{k}": [np.nan] for k in scoring}
        else:
            logger.warning(
                "Conjunto de treino tem apenas uma classe de contamination_status - "
                "pulando validação cruzada para '%s' (métricas de CV ficarão como NaN).",
                model_name,
            )
            cv_result = {f"test_{k}": [np.nan] for k in scoring}

        model.fit(x_train, y_train)
        y_pred = model.predict(x_test)
        y_proba = model.predict_proba(x_test)[:, 1] if hasattr(model, "predict_proba") else np.full(len(y_pred), np.nan)

        metrics_rows.append(
            {
                "model": model_name,
                "cv_balanced_accuracy_mean": float(np.mean(cv_result["test_balanced_accuracy"])),
                "cv_f1_mean": float(np.mean(cv_result["test_f1"])),
                "cv_precision_mean": float(np.mean(cv_result["test_precision"])),
                "cv_recall_mean": float(np.mean(cv_result["test_recall"])),
                "test_balanced_accuracy": balanced_accuracy_score(y_test, y_pred),
                "test_f1": f1_score(y_test, y_pred, zero_division=0),
                "test_precision": precision_score(y_test, y_pred, zero_division=0),
                "test_sensitivity": recall_score(y_test, y_pred, zero_division=0),
                "test_specificity": _specificity(y_test, y_pred),
                "test_roc_auc": (
                    roc_auc_score(y_test, y_proba) if np.isfinite(y_proba).all() and y_test.nunique() > 1 else np.nan
                ),
                "confusion_matrix": json.dumps(confusion_matrix(y_test, y_pred, labels=[0, 1]).tolist()),
            }
        )

        predictions_rows.append(
            pd.DataFrame(
                {
                    "model": model_name,
                    "sample_uid": groups.iloc[test_idx].to_numpy(),
                    "y_true": y_test.to_numpy(),
                    "y_pred": y_pred,
                    "y_proba": y_proba,
                }
            )
        )

    metrics = pd.DataFrame(metrics_rows).sort_values("test_balanced_accuracy", ascending=False)
    predictions = pd.concat(predictions_rows, ignore_index=True)
    return metrics, predictions


def summarize_relevant_regions(wide: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [c for c in wide.columns if c.startswith("I_")]
    x, y, _ = prepare_features(wide)

    model = Pipeline(
        [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42))]
    )
    model.fit(x, y)
    coefs = np.abs(model.named_steps["clf"].coef_[0][: len(feature_cols)])
    importance = pd.DataFrame({"feature": feature_cols, "importance_abs_coef": coefs}).sort_values(
        "importance_abs_coef", ascending=False
    )
    return importance.head(30)


def export(
    output_dir: str | Path,
    measurements: pd.DataFrame,
    wide: pd.DataFrame,
    samples: pd.DataFrame | None,
    model_metrics: pd.DataFrame | None,
    predictions: pd.DataFrame | None,
    feature_importance: pd.DataFrame | None,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    measurements.to_csv(out / "voltammograms_long.csv", index=False)
    wide.to_csv(out / "voltammograms_wide.csv", index=False)
    if samples is not None:
        samples.to_csv(out / "metadata_experiments.csv", index=False)
    if model_metrics is not None:
        model_metrics.to_csv(out / "model_metrics.csv", index=False)
    if predictions is not None:
        predictions.to_csv(out / "test_predictions.csv", index=False)
    if feature_importance is not None:
        feature_importance.to_csv(out / "feature_importance_regions.csv", index=False)

    with sqlite3.connect(out / "biosensor_case.db") as conn:
        measurements.to_sql("voltammograms_long", conn, if_exists="replace", index=False)
        wide.to_sql("voltammograms_wide", conn, if_exists="replace", index=False)
        if samples is not None:
            samples.to_sql("metadata_experiments", conn, if_exists="replace", index=False)
        if model_metrics is not None:
            model_metrics.to_sql("model_metrics", conn, if_exists="replace", index=False)
        if predictions is not None:
            predictions.to_sql("test_predictions", conn, if_exists="replace", index=False)
        if feature_importance is not None:
            feature_importance.to_sql("feature_importance_regions", conn, if_exists="replace", index=False)


def run(
    prepared_dir: str | Path,
    output_dir: str | Path,
    random_state: int = 42,
    keep_flags: tuple[str, ...] = ("PASS",),
) -> dict[str, pd.DataFrame]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    measurements, samples = load_prepared(prepared_dir)
    measurements = filter_by_quality(measurements, keep_flags=keep_flags)
    wide = build_wide_table(measurements)

    model_metrics = predictions = feature_importance = None
    eligible = wide.dropna(subset=["contamination_status"]) if "contamination_status" in wide.columns else pd.DataFrame()
    if len(eligible) >= MIN_ROWS_FOR_MODELING and eligible["contamination_status"].nunique() > 1:
        model_metrics, predictions = train_and_evaluate(wide, random_state=random_state)
        feature_importance = summarize_relevant_regions(wide)
        logger.info("Modelagem concluída. Melhor modelo (balanced accuracy no teste):\n%s",
                     model_metrics[["model", "test_balanced_accuracy"]].to_string(index=False))
    else:
        logger.warning(
            "Dados insuficientes para modelagem (linhas com contamination_status válido=%d, "
            "classes distintas=%s). É necessário >= %d linhas e 2 classes.",
            len(eligible),
            eligible["contamination_status"].nunique() if not eligible.empty else 0,
            MIN_ROWS_FOR_MODELING,
        )

    export(output_dir, measurements, wide, samples, model_metrics, predictions, feature_importance)

    logger.info("Medições (linhas de sinal): %d", len(measurements))
    logger.info("Medições únicas (wide): %d", len(wide))
    logger.info("Saídas gravadas em %s", Path(output_dir).resolve())

    return {
        "measurements": measurements,
        "wide": wide,
        "samples": samples,
        "model_metrics": model_metrics,
        "predictions": predictions,
        "feature_importance": feature_importance,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingere dados já preparados: features, modelagem e exportação.")
    parser.add_argument("--prepared-dir", type=Path, required=True, help="Diretório com prepared_measurements.csv (saída do data_preparation.py).")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="Diretório de saída para os resultados.")
    parser.add_argument("--random-state", type=int, default=42, help="Semente aleatória para modelagem.")
    parser.add_argument(
        "--keep-flags", nargs="+", default=["PASS"],
        help="Valores de qc_flag a manter antes de modelar (padrão: PASS). Ex: --keep-flags PASS REVIEW",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args.prepared_dir, args.output_dir, random_state=args.random_state, keep_flags=tuple(args.keep_flags))


if __name__ == "__main__":
    main()
