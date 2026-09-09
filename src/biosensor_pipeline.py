from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
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


FILE_EXTENSIONS = {".csv", ".txt", ".xlsx", ".xls"}
CONDITION_MAP = {
    "clean": ["limpo", "clean", "blank"],
    "capture": ["captura", "capture", "functionalized"],
    "target_contact": ["alvo", "target", "contato", "contaminado", "bacteria"],
}


@dataclass
class ValidationResult:
    duplicates: int
    missing_values: int
    format_errors: list[str]
    incomplete_voltammograms: list[str]
    point_count_summary: dict[str, Any]
    discrepant_replicates: list[str]
    interfile_inconsistencies: list[str]



def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _hash_id(*parts: str) -> str:
    payload = "|".join(str(p) for p in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = {c.lower().strip(): c for c in df.columns}
    for candidate in candidates:
        if candidate in cols:
            return cols[candidate]
    return None


def _read_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    sep = ","
    if path.suffix.lower() == ".txt":
        sep = None
    return pd.read_csv(path, sep=sep, engine="python")


def _extract_metadata(filename: str) -> dict[str, str]:
    stem = _slug(Path(filename).stem)
    meta = {
        "raw_file": filename,
        "bacteria_target": "unknown",
        "sample_code": "unknown",
        "replicate_code": "r0",
        "lot_code": "l0",
        "batch_code": "b0",
        "sensor_condition": "unknown",
        "experimental_condition": "unknown",
    }

    patterns = {
        "bacteria_target": r"(ecoli|salmonella|listeria|staph[a-z0-9]*)",
        "sample_code": r"(?:sample|amostra)_?([a-z0-9]+)",
        "replicate_code": r"(?:rep|replicata|r)_?([0-9]+)",
        "lot_code": r"(?:lote|lot|l)_?([0-9]+)",
        "batch_code": r"(?:batch|batelada|b)_?([0-9]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, stem)
        if match:
            value = match.group(1)
            meta[key] = f"{key.split('_')[0]}_{value}" if key.endswith("_code") else value

    for condition, keywords in CONDITION_MAP.items():
        if any(k in stem for k in keywords):
            meta["sensor_condition"] = condition
            break

    meta["experimental_condition"] = stem
    return meta


def load_raw_voltammograms(input_dir: str | Path) -> pd.DataFrame:
    input_path = Path(input_dir)
    files = sorted([p for p in input_path.rglob("*") if p.suffix.lower() in FILE_EXTENSIONS])
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo suportado encontrado em {input_path}")

    frames: list[pd.DataFrame] = []
    for file in files:
        df = _read_file(file)
        meta = _extract_metadata(file.name)

        potential_col = _find_column(df, ["potential", "potencial", "e", "voltage", "v"])
        current_col = _find_column(df, ["current", "corrente", "i", "ua", "ma"])

        if potential_col is None or current_col is None:
            df.columns = [_slug(c) for c in df.columns]
            potential_col = _find_column(df, ["potential", "potencial", "e", "voltage", "v"])
            current_col = _find_column(df, ["current", "corrente", "i", "ua", "ma"])

        if potential_col is None or current_col is None:
            raise ValueError(
                f"Arquivo {file.name} não possui colunas reconhecidas de potencial/corrente"
            )

        renamed = df.rename(columns={potential_col: "potential", current_col: "current"})
        use_cols = ["potential", "current"]
        for c in ["sensor", "amostra", "sample", "replicate", "replicata", "bacteria", "condition"]:
            found = _find_column(renamed, [c])
            if found and found not in use_cols:
                use_cols.append(found)

        subset = renamed[use_cols].copy()
        subset["source_file"] = str(file)
        for k, v in meta.items():
            subset[k] = v
        frames.append(subset)

    raw = pd.concat(frames, ignore_index=True)
    raw["potential"] = pd.to_numeric(raw["potential"], errors="coerce")
    raw["current"] = pd.to_numeric(raw["current"], errors="coerce")

    raw["sample_id"] = raw.get("sample", raw.get("amostra", raw["sample_code"]))
    raw["replicate_id"] = raw.get("replicate", raw.get("replicata", raw["replicate_code"]))
    raw["sensor_id"] = raw.get("sensor", raw["sensor_condition"])

    raw["measurement_uid"] = raw.apply(
        lambda r: _hash_id(
            r["source_file"], r["sample_id"], r["replicate_id"], r["sensor_id"], r["sensor_condition"]
        ),
        axis=1,
    )
    raw["experiment_uid"] = raw.apply(
        lambda r: _hash_id(r["bacteria_target"], r["lot_code"], r["batch_code"], r["experimental_condition"]),
        axis=1,
    )
    raw["point_index"] = raw.groupby("measurement_uid").cumcount()
    return raw


def validate_voltammograms(raw_df: pd.DataFrame) -> ValidationResult:
    duplicates = int(raw_df.duplicated().sum())
    missing_values = int(raw_df[["potential", "current"]].isna().sum().sum())

    format_errors = []
    if raw_df["potential"].isna().any():
        format_errors.append("Potenciais não numéricos detectados")
    if raw_df["current"].isna().any():
        format_errors.append("Correntes não numéricas detectadas")

    point_counts = raw_df.groupby("measurement_uid").size()
    median_points = int(point_counts.median()) if not point_counts.empty else 0
    incomplete = point_counts[point_counts < median_points].index.tolist()

    peak_current = (
        raw_df.groupby(["sample_id", "sensor_condition", "replicate_id"], dropna=False)["current"]
        .max()
        .reset_index(name="peak_current")
    )
    discrepant = []
    if not peak_current.empty:
        grp = peak_current.groupby(["sample_id", "sensor_condition"], dropna=False)["peak_current"]
        mean = grp.transform("mean")
        std = grp.transform("std").replace(0, np.nan)
        z = (peak_current["peak_current"] - mean).abs() / std
        discrepant = peak_current.loc[z > 2.5, "replicate_id"].astype(str).tolist()

    inconsistencies = []
    potentials_per_file = raw_df.groupby("source_file")["potential"].nunique()
    if potentials_per_file.nunique() > 1:
        inconsistencies.append("Número de potenciais distintos varia entre arquivos")

    return ValidationResult(
        duplicates=duplicates,
        missing_values=missing_values,
        format_errors=format_errors,
        incomplete_voltammograms=incomplete,
        point_count_summary={
            "min": int(point_counts.min()) if not point_counts.empty else 0,
            "max": int(point_counts.max()) if not point_counts.empty else 0,
            "median": median_points,
        },
        discrepant_replicates=discrepant,
        interfile_inconsistencies=inconsistencies,
    )


def _prepare_ids(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["sample_uid"] = result["sample_id"].astype(str).map(lambda v: _hash_id("sample", v))
    result["sensor_uid"] = result["sensor_id"].astype(str).map(lambda v: _hash_id("sensor", v))
    result["replicate_uid"] = result["replicate_id"].astype(str).map(lambda v: _hash_id("replicate", v))
    return result


def build_structured_tables(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    enriched = _prepare_ids(raw_df)

    long_table = enriched[
        [
            "experiment_uid",
            "measurement_uid",
            "sample_uid",
            "sensor_uid",
            "replicate_uid",
            "sample_id",
            "sensor_id",
            "replicate_id",
            "sensor_condition",
            "bacteria_target",
            "lot_code",
            "batch_code",
            "potential",
            "current",
            "point_index",
            "source_file",
        ]
    ].copy()

    wide = (
        long_table.pivot_table(
            index=[
                "experiment_uid",
                "measurement_uid",
                "sample_uid",
                "sample_id",
                "sensor_condition",
                "bacteria_target",
                "lot_code",
                "batch_code",
            ],
            columns="potential",
            values="current",
            aggfunc="mean",
        )
        .sort_index(axis=1)
        .reset_index()
    )
    wide.columns = [str(c) if not isinstance(c, float) else f"I_{c:.6f}" for c in wide.columns]

    metadata = (
        long_table[
            [
                "experiment_uid",
                "measurement_uid",
                "sample_uid",
                "sensor_uid",
                "replicate_uid",
                "sample_id",
                "sensor_id",
                "replicate_id",
                "sensor_condition",
                "bacteria_target",
                "lot_code",
                "batch_code",
                "source_file",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    return long_table, wide, metadata


def _target_from_condition(condition: str) -> int:
    return 1 if condition == "target_contact" else 0


def prepare_features(analytical_wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    feature_cols = [c for c in analytical_wide.columns if c.startswith("I_")]
    df = analytical_wide.copy()
    if not feature_cols:
        raise ValueError("Nenhuma feature de corrente encontrada para modelagem")

    df["peak_current"] = df[feature_cols].max(axis=1)
    df["min_current"] = df[feature_cols].min(axis=1)
    df["delta_current"] = df["peak_current"] - df["min_current"]

    x = df[feature_cols + ["peak_current", "min_current", "delta_current"]].fillna(0.0)
    y = df["sensor_condition"].map(_target_from_condition)
    groups = df["sample_uid"]
    return x, y, groups


def _specificity_from_confusion(y_true: pd.Series, y_pred: np.ndarray) -> float:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    if cm.shape != (2, 2):
        return float("nan")
    tn, fp, _, _ = cm.ravel()
    return tn / (tn + fp) if (tn + fp) else float("nan")


def train_and_evaluate(analytical_wide: pd.DataFrame, random_state: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    x, y, groups = prepare_features(analytical_wide)

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    train_idx, test_idx = next(splitter.split(x, y, groups=groups))

    x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    g_train = groups.iloc[train_idx]

    cv = GroupKFold(n_splits=max(2, min(5, g_train.nunique())))

    models: dict[str, Any] = {
        "baseline_log_reg": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_state)),
            ]
        ),
        "lda": Pipeline([("scaler", StandardScaler()), ("clf", LinearDiscriminantAnalysis())]),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced",
            random_state=random_state,
            min_samples_leaf=1,
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
        cv_result = cross_validate(
            model,
            x_train,
            y_train,
            groups=g_train,
            cv=cv,
            scoring=scoring,
            error_score="raise",
        )

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
                "test_specificity": _specificity_from_confusion(y_test, y_pred),
                "test_roc_auc": roc_auc_score(y_test, y_proba) if np.isfinite(y_proba).all() and y_test.nunique() > 1 else np.nan,
                "confusion_matrix": json.dumps(confusion_matrix(y_test, y_pred, labels=[0, 1]).tolist()),
            }
        )

        pred_df = pd.DataFrame(
            {
                "model": model_name,
                "sample_uid": groups.iloc[test_idx].to_numpy(),
                "y_true": y_test.to_numpy(),
                "y_pred": y_pred,
                "y_proba": y_proba,
            }
        )
        predictions_rows.append(pred_df)

    metrics = pd.DataFrame(metrics_rows).sort_values("test_balanced_accuracy", ascending=False)
    predictions = pd.concat(predictions_rows, ignore_index=True)
    return metrics, predictions


def summarize_relevant_regions(analytical_wide: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [c for c in analytical_wide.columns if c.startswith("I_")]
    x, y, _ = prepare_features(analytical_wide)

    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
        ]
    )
    model.fit(x, y)
    coefs = np.abs(model.named_steps["clf"].coef_[0][: len(feature_cols)])
    importance = pd.DataFrame({"feature": feature_cols, "importance_abs_coef": coefs}).sort_values(
        "importance_abs_coef", ascending=False
    )
    return importance.head(30)


def export_database(
    output_dir: str | Path,
    long_table: pd.DataFrame,
    wide_table: pd.DataFrame,
    metadata: pd.DataFrame,
    validation: ValidationResult,
    model_metrics: pd.DataFrame | None = None,
    predictions: pd.DataFrame | None = None,
    feature_importance: pd.DataFrame | None = None,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    long_table.to_csv(out / "voltammograms_long.csv", index=False)
    wide_table.to_csv(out / "voltammograms_wide.csv", index=False)
    metadata.to_csv(out / "metadata_experiments.csv", index=False)

    if model_metrics is not None:
        model_metrics.to_csv(out / "model_metrics.csv", index=False)
    if predictions is not None:
        predictions.to_csv(out / "test_predictions.csv", index=False)
    if feature_importance is not None:
        feature_importance.to_csv(out / "feature_importance_regions.csv", index=False)

    validation_df = pd.DataFrame(
        [
            {
                "duplicates": validation.duplicates,
                "missing_values": validation.missing_values,
                "format_errors": "; ".join(validation.format_errors),
                "incomplete_voltammograms": "; ".join(validation.incomplete_voltammograms),
                "point_count_min": validation.point_count_summary["min"],
                "point_count_median": validation.point_count_summary["median"],
                "point_count_max": validation.point_count_summary["max"],
                "discrepant_replicates": "; ".join(validation.discrepant_replicates),
                "interfile_inconsistencies": "; ".join(validation.interfile_inconsistencies),
            }
        ]
    )
    validation_df.to_csv(out / "validation_report.csv", index=False)

    with sqlite3.connect(out / "biosensor_case.db") as conn:
        long_table.to_sql("voltammograms_long", conn, if_exists="replace", index=False)
        wide_table.to_sql("voltammograms_wide", conn, if_exists="replace", index=False)
        metadata.to_sql("metadata_experiments", conn, if_exists="replace", index=False)
        validation_df.to_sql("validation_report", conn, if_exists="replace", index=False)
        if model_metrics is not None:
            model_metrics.to_sql("model_metrics", conn, if_exists="replace", index=False)
        if predictions is not None:
            predictions.to_sql("test_predictions", conn, if_exists="replace", index=False)
        if feature_importance is not None:
            feature_importance.to_sql("feature_importance_regions", conn, if_exists="replace", index=False)


def run_pipeline(input_dir: str | Path, output_dir: str | Path, random_state: int = 42) -> dict[str, pd.DataFrame]:
    raw = load_raw_voltammograms(input_dir)
    validation = validate_voltammograms(raw)
    long_table, wide_table, metadata = build_structured_tables(raw)

    model_metrics = predictions = feature_importance = None
    if wide_table["sensor_condition"].nunique() > 1 and len(wide_table) >= 8:
        model_metrics, predictions = train_and_evaluate(wide_table, random_state=random_state)
        feature_importance = summarize_relevant_regions(wide_table)

    export_database(
        output_dir=output_dir,
        long_table=long_table,
        wide_table=wide_table,
        metadata=metadata,
        validation=validation,
        model_metrics=model_metrics,
        predictions=predictions,
        feature_importance=feature_importance,
    )

    return {
        "raw": raw,
        "long": long_table,
        "wide": wide_table,
        "metadata": metadata,
        "model_metrics": model_metrics,
        "predictions": predictions,
        "feature_importance": feature_importance,
    }
