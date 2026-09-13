"""
advanced_modeling.py
=====================

Extensão experimental do pipeline: testa se as melhorias discutidas na defesa
de fato aumentam a acurácia, comparando de forma controlada contra o baseline
(ingest_pipeline.py).

Melhorias testadas:
1. Features de DIFERENÇA entre estágios do sensor (capture_probe_16S_rRNA -
   capture_probe, e vs. carbon_clean) por amostra+replicata, em vez de tratar
   cada estágio como observação independente.
2. Suavização (Savitzky-Golay) antes de extrair descritores.
3. Descritores mais ricos: área sob a curva (AUC), potencial do pico, largura
   do pico — além de peak/min/delta já usados.
4. Modelos adicionais: SVM (RBF) e Gradient Boosting.
5. Validação cruzada mais robusta: múltiplas seeds de split treino/teste,
   reportando média ± desvio (em vez de um único split).
6. Otimização de threshold de decisão (Youden's J) em vez do corte fixo 0.5.

Uso:
    python src/advanced_modeling.py --prepared-dir prepared --output-dir outputs_advanced
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score, roc_curve
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

logger = logging.getLogger("advanced_modeling")

_trapz = getattr(np, "trapezoid", None) or np.trapz
STAGES = ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"]


# --------------------------------------------------------------------------- FEATURES

def _smooth(y: np.ndarray, window: int = 11, poly: int = 3) -> np.ndarray:
    window = min(window, len(y) - (1 - len(y) % 2))
    if window < poly + 2:
        return y
    if window % 2 == 0:
        window -= 1
    return savgol_filter(y, window_length=window, polyorder=poly)


def _curve_descriptors(potential: np.ndarray, current: np.ndarray, prefix: str) -> dict:
    peak_idx = int(np.argmax(current))
    peak = current[peak_idx]
    baseline = np.median(current)  # aproximação robusta de linha de base local
    half = baseline + (peak - baseline) / 2
    above = current >= half
    width = potential[above].max() - potential[above].min() if above.any() else 0.0
    return {
        f"{prefix}_peak_current": float(peak),
        f"{prefix}_min_current": float(current.min()),
        f"{prefix}_delta_current": float(peak - current.min()),
        f"{prefix}_auc": float(_trapz(current, potential)),
        f"{prefix}_peak_potential": float(potential[peak_idx]),
        f"{prefix}_peak_width": float(width),
    }


def build_stage_diff_dataset(
    measurements: pd.DataFrame, keep_flags: tuple[str, ...] = ("PASS",), smooth: bool = True,
    include_full_delta_curve: bool = True,
) -> pd.DataFrame:
    """1 linha por (sample_id, replicate_id), com descritores por estágio + deltas entre estágios."""
    df = measurements[measurements["qc_flag"].isin(keep_flags)].copy()

    rows = []
    grouped = df.groupby(["sample_id", "replicate_id"])
    for (sample_id, replicate_id), g in grouped:
        stage_curves = {}
        ok = True
        for stage in STAGES:
            sg = g[g["sensor_state"] == stage].sort_values("potential_v")
            if sg.empty:
                ok = False
                break
            pot = sg["potential_v"].to_numpy()
            cur = sg["current_ua"].to_numpy()
            if smooth:
                cur = _smooth(cur)
            stage_curves[stage] = (pot, cur)
        if not ok:
            continue  # replicata sem os 3 estágios disponíveis (após filtro de qualidade) - descarta

        row: dict[str, Any] = {"sample_id": sample_id, "replicate_id": replicate_id}
        row["contamination_status"] = g["contamination_status"].iloc[0]
        row["sensor_lot"] = g["sensor_lot"].iloc[0] if "sensor_lot" in g.columns else np.nan
        row["target_bacterium"] = g["target_bacterium"].iloc[0]

        for stage in STAGES:
            pot, cur = stage_curves[stage]
            row.update(_curve_descriptors(pot, cur, prefix=stage))

        # deltas entre estágios: a hipótese central do sensor
        pot0, cur0 = stage_curves["carbon_clean"]
        pot1, cur1 = stage_curves["capture_probe"]
        pot2, cur2 = stage_curves["capture_probe_16S_rRNA"]

        delta_curve_21 = cur2 - cur1  # sinal do "contato com o alvo"
        delta_curve_20 = cur2 - cur0

        row["delta_peak_21"] = row["capture_probe_16S_rRNA_peak_current"] - row["capture_probe_peak_current"]
        row["delta_peak_20"] = row["capture_probe_16S_rRNA_peak_current"] - row["carbon_clean_peak_current"]
        row["delta_auc_21"] = row["capture_probe_16S_rRNA_auc"] - row["capture_probe_auc"]
        row["delta_auc_20"] = row["capture_probe_16S_rRNA_auc"] - row["carbon_clean_auc"]
        row["delta_peak_potential_21"] = row["capture_probe_16S_rRNA_peak_potential"] - row["capture_probe_peak_potential"]

        if include_full_delta_curve:
            for i, p in enumerate(pot1):
                row[f"D21_{p:.3f}"] = delta_curve_21[i]

        rows.append(row)

    result = pd.DataFrame(rows)
    logger.info("Dataset por amostra+replicata: %d linhas (de %d grupos originais)", len(result), len(grouped))
    return result


def feature_columns(dataset: pd.DataFrame, feature_set: str) -> list[str]:
    if feature_set == "stage_diff_summary":
        return [c for c in dataset.columns if c not in
                {"sample_id", "replicate_id", "contamination_status", "sensor_lot", "target_bacterium"}
                and not c.startswith("D21_")]
    if feature_set == "stage_diff_full_curve":
        return [c for c in dataset.columns if c not in
                {"sample_id", "replicate_id", "contamination_status", "sensor_lot", "target_bacterium"}]
    raise ValueError(feature_set)


# --------------------------------------------------------------------------- MODELOS

def build_models(random_state: int) -> dict[str, Any]:
    return {
        "baseline_log_reg": Pipeline([("scaler", StandardScaler()),
                                       ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=random_state))]),
        "lda": Pipeline([("scaler", StandardScaler()), ("clf", LinearDiscriminantAnalysis())]),
        "random_forest": RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=random_state, min_samples_leaf=1),
        "svm_rbf": Pipeline([("scaler", StandardScaler()),
                              ("clf", SVC(kernel="rbf", probability=True, class_weight="balanced", random_state=random_state))]),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=200, random_state=random_state),
    }


def _specificity(y_true, y_pred) -> float:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, _, _ = cm.ravel()
    return tn / (tn + fp) if (tn + fp) else float("nan")


def youden_threshold(y_true, y_proba) -> float:
    fpr, tpr, thr = roc_curve(y_true, y_proba)
    j = tpr - fpr
    return float(thr[np.argmax(j)])


# --------------------------------------------------------------------------- EXPERIMENTO

def run_multiseed_comparison(
    dataset: pd.DataFrame, feature_set: str, seeds: list[int],
) -> pd.DataFrame:
    cols = feature_columns(dataset, feature_set)
    x = dataset[cols].fillna(0.0)
    y = dataset["contamination_status"].astype(int)
    groups = dataset["sample_id"]

    rows = []
    for seed in seeds:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
        train_idx, test_idx = next(splitter.split(x, y, groups=groups))
        x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        if y_train.nunique() < 2 or y_test.nunique() < 2:
            continue

        for model_name, model in build_models(seed).items():
            model.fit(x_train, y_train)
            y_pred = model.predict(x_test)
            y_proba = model.predict_proba(x_test)[:, 1] if hasattr(model, "predict_proba") else None

            entry = {
                "feature_set": feature_set,
                "model": model_name,
                "seed": seed,
                "balanced_accuracy": balanced_accuracy_score(y_test, y_pred),
                "sensitivity": (y_pred[y_test == 1] == 1).mean() if (y_test == 1).any() else np.nan,
                "specificity": _specificity(y_test, y_pred),
                "roc_auc": roc_auc_score(y_test, y_proba) if y_proba is not None and np.isfinite(y_proba).all() else np.nan,
            }

            if y_proba is not None and np.isfinite(y_proba).all():
                thr = youden_threshold(y_test, y_proba)
                y_pred_opt = (y_proba >= thr).astype(int)
                entry["balanced_accuracy_opt_threshold"] = balanced_accuracy_score(y_test, y_pred_opt)
                entry["threshold_used"] = thr
            else:
                entry["balanced_accuracy_opt_threshold"] = np.nan
                entry["threshold_used"] = np.nan

            rows.append(entry)

    return pd.DataFrame(rows)


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    agg = results.groupby(["feature_set", "model"]).agg(
        balanced_accuracy_mean=("balanced_accuracy", "mean"),
        balanced_accuracy_std=("balanced_accuracy", "std"),
        balanced_accuracy_opt_mean=("balanced_accuracy_opt_threshold", "mean"),
        sensitivity_mean=("sensitivity", "mean"),
        specificity_mean=("specificity", "mean"),
        roc_auc_mean=("roc_auc", "mean"),
        roc_auc_std=("roc_auc", "std"),
        n_seeds=("seed", "nunique"),
    ).reset_index()
    return agg.sort_values("balanced_accuracy_mean", ascending=False)


def detailed_report_best_config(
    dataset: pd.DataFrame, feature_set: str, model_name: str, seed: int = 42,
) -> dict:
    """Relatório detalhado (matriz de confusão, threshold ótimo) de UMA config, para uso em slides/relatório."""
    cols = feature_columns(dataset, feature_set)
    x = dataset[cols].fillna(0.0)
    y = dataset["contamination_status"].astype(int)
    groups = dataset["sample_id"]

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
    train_idx, test_idx = next(splitter.split(x, y, groups=groups))
    x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    model = build_models(seed)[model_name]
    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)
    y_proba = model.predict_proba(x_test)[:, 1]

    thr = youden_threshold(y_test, y_proba)
    y_pred_opt = (y_proba >= thr).astype(int)

    return {
        "feature_set": feature_set,
        "model": model_name,
        "seed": seed,
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
        "n_features": int(x.shape[1]),
        "confusion_matrix_default": confusion_matrix(y_test, y_pred, labels=[0, 1]).tolist(),
        "confusion_matrix_opt_threshold": confusion_matrix(y_test, y_pred_opt, labels=[0, 1]).tolist(),
        "threshold_opt": float(thr),
        "balanced_accuracy_default": float(balanced_accuracy_score(y_test, y_pred)),
        "balanced_accuracy_opt": float(balanced_accuracy_score(y_test, y_pred_opt)),
        "roc_auc": float(roc_auc_score(y_test, y_proba)),
    }


def run(prepared_dir: str | Path, output_dir: str | Path, seeds: list[int], keep_flags: tuple[str, ...]) -> pd.DataFrame:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    prepared_path = Path(prepared_dir)
    measurements = pd.read_csv(prepared_path / "prepared_measurements.csv")

    logger.info("Construindo dataset de diferença entre estágios (1 linha por amostra+replicata)...")
    stage_dataset = build_stage_diff_dataset(measurements, keep_flags=keep_flags)

    all_results = []
    for feature_set in ["stage_diff_summary", "stage_diff_full_curve"]:
        logger.info("Rodando comparação multi-seed para feature_set=%s ...", feature_set)
        res = run_multiseed_comparison(stage_dataset, feature_set, seeds)
        all_results.append(res)

    results = pd.concat(all_results, ignore_index=True)
    summary = summarize(results)

    best = summary.iloc[0]
    detailed = detailed_report_best_config(stage_dataset, best["feature_set"], best["model"], seed=42)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results.to_csv(out / "advanced_modeling_all_seeds.csv", index=False)
    summary.to_csv(out / "advanced_modeling_summary.csv", index=False)
    stage_dataset.to_csv(out / "stage_diff_dataset.csv", index=False)
    import json
    with open(out / "advanced_modeling_best_config_detail.json", "w") as f:
        json.dump(detailed, f, indent=2, ensure_ascii=False)

    logger.info("\n%s", summary.to_string(index=False))
    logger.info("Melhor config detalhada: %s", detailed)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Testa melhorias de feature engineering e modelos adicionais.")
    p.add_argument("--prepared-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=Path("outputs_advanced"))
    p.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    p.add_argument("--keep-flags", nargs="+", default=["PASS"])
    return p


def main() -> None:
    args = build_parser().parse_args()
    run(args.prepared_dir, args.output_dir, args.seeds, tuple(args.keep_flags))


if __name__ == "__main__":
    main()
