"""
data_preparation.py
====================

Etapa 1 do pipeline: "arrumar os dados".

Varre um diretório de entrada, identifica cada arquivo .csv/.txt/.xlsx/.xls
PELO CONJUNTO DE COLUNAS (schema), não pelo nome do arquivo, e classifica em
um dos três papéis conhecidos (ver Dicionario_Dados.csv):

- SIGNAL   -> voltamogramas brutos (measurement_id, potential_V, current_uA, ...)
- METADATA -> metadados de medição (measurement_id, contamination_status, qc_flag, ...)
- PLATING  -> referência microbiológica por plaqueamento (sample_id, colony_count, ...)

Isso significa que, se amanhã chegar um novo lote de arquivos com esses mesmos
formatos (mesmo com nomes de arquivo diferentes), o script reconhece e junta
automaticamente sem precisar de nenhuma alteração.

Saídas (em --output-dir):
- prepared_measurements.csv : formato longo, 1 linha por ponto do voltamograma,
  já enriquecido com metadados (sample_id, replicate_id, sensor_state,
  sensor_state_code, target_bacterium, contamination_status, qc_flag).
- prepared_samples.csv      : 1 linha por amostra, com dados de referência de
  plaqueamento agregados (quando disponíveis).
- preparation_report.csv    : relatório de validação/qualidade da junção.

Uso:
    python src/data_preparation.py --input-dir Dados --output-dir prepared
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger("data_preparation")

FILE_EXTENSIONS = {".csv", ".txt", ".xlsx", ".xls"}

# Colunas mínimas que definem cada papel. Um arquivo só é classificado como
# tal se contiver TODAS as colunas obrigatórias daquele papel.
ROLE_REQUIRED_COLUMNS: dict[str, set[str]] = {
    "signal": {"measurement_id", "potential_v", "current_ua"},
    "metadata": {"measurement_id", "sample_id", "contamination_status"},
    "plating": {"sample_id", "colony_count"},
}

# Colunas opcionais que, se presentes, são aproveitadas de cada papel.
ROLE_OPTIONAL_COLUMNS: dict[str, list[str]] = {
    "signal": ["scan_index", "sample_id", "replicate_id", "sensor_state", "target_bacterium"],
    "metadata": [
        "replicate_id",
        "sensor_id",
        "target_bacterium",
        "species_code",
        "sensor_state",
        "sensor_state_code",
        "surface_type",
        "sensor_lot",
        "experimental_batch",
        "operator_id",
        "measurement_date",
        "incubation_time_h",
        "incubation_temperature_c",
        "sample_mean_cfu_ml",
        "sample_log10_mean_cfu_ml",
        "qc_flag",
    ],
    "plating": [
        "plating_replicate_id",
        "target_bacterium",
        "contamination_status",
        "plated_volume_ml",
        "dilution_exponent",
        "dilution_label",
        "plating_qualifier",
        "calculated_cfu_ml",
        "log10_cfu_ml",
    ],
}

VALID_QC_FLAGS = {"PASS", "REVIEW", "FAIL"}


@dataclass
class PreparationReport:
    files_found: list[str] = field(default_factory=list)
    files_classified: dict[str, str] = field(default_factory=dict)
    files_unclassified: list[str] = field(default_factory=list)
    signal_rows: int = 0
    metadata_rows: int = 0
    plating_rows: int = 0
    measurements_without_metadata: int = 0
    metadata_without_signal: int = 0
    samples_without_plating: int = 0
    duplicate_signal_points: int = 0
    duplicate_metadata_ids: int = 0
    invalid_qc_flags: int = 0
    missing_potential_or_current: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        row = {
            "files_found": "; ".join(self.files_found),
            "files_classified": "; ".join(f"{k} -> {v}" for k, v in self.files_classified.items()),
            "files_unclassified": "; ".join(self.files_unclassified),
            "signal_rows": self.signal_rows,
            "metadata_rows": self.metadata_rows,
            "plating_rows": self.plating_rows,
            "measurements_without_metadata": self.measurements_without_metadata,
            "metadata_without_signal": self.metadata_without_signal,
            "samples_without_plating": self.samples_without_plating,
            "duplicate_signal_points": self.duplicate_signal_points,
            "duplicate_metadata_ids": self.duplicate_metadata_ids,
            "invalid_qc_flags": self.invalid_qc_flags,
            "missing_potential_or_current": self.missing_potential_or_current,
            "notes": " | ".join(self.notes),
        }
        return pd.DataFrame([row])


def _slug(text: str) -> str:
    return str(text).strip().lower().replace(" ", "_").replace("-", "_")


def _read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [_slug(c) for c in df.columns]
    return df


def classify_file(df: pd.DataFrame) -> str | None:
    """Classifica um DataFrame já lido em 'signal', 'metadata', 'plating' ou None."""
    cols = set(df.columns)
    for role, required in ROLE_REQUIRED_COLUMNS.items():
        if required.issubset(cols):
            return role
    return None


def discover_and_classify(input_dir: str | Path, report: PreparationReport) -> dict[str, list[pd.DataFrame]]:
    input_path = Path(input_dir)
    files = sorted(p for p in input_path.rglob("*") if p.suffix.lower() in FILE_EXTENSIONS)
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo suportado encontrado em {input_path}")

    buckets: dict[str, list[pd.DataFrame]] = {"signal": [], "metadata": [], "plating": []}
    for file in files:
        report.files_found.append(file.name)
        df = _read_any(file)
        role = classify_file(df)
        if role is None:
            report.files_unclassified.append(file.name)
            logger.warning(
                "Arquivo '%s' não bate com nenhum schema conhecido (colunas: %s) - ignorado.",
                file.name,
                sorted(df.columns),
            )
            continue
        report.files_classified[file.name] = role
        df["__source_file"] = file.name
        buckets[role].append(df)

    return buckets


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_prepared_measurements(
    signal_df: pd.DataFrame, metadata_df: pd.DataFrame, report: PreparationReport
) -> pd.DataFrame:
    if signal_df.empty:
        raise ValueError(
            "Nenhum arquivo de SINAL (measurement_id, potential_v, current_ua) foi encontrado."
        )

    signal_df = signal_df.copy()
    signal_df["potential_v"] = pd.to_numeric(signal_df["potential_v"], errors="coerce")
    signal_df["current_ua"] = pd.to_numeric(signal_df["current_ua"], errors="coerce")

    missing_signal = int(signal_df[["potential_v", "current_ua"]].isna().any(axis=1).sum())
    report.missing_potential_or_current = missing_signal
    if missing_signal:
        report.notes.append(f"{missing_signal} pontos de sinal com potencial/corrente ausente ou não numérico.")

    dup_points = int(
        signal_df.duplicated(subset=[c for c in ["measurement_id", "scan_index"] if c in signal_df.columns]).sum()
    )
    report.duplicate_signal_points = dup_points
    if dup_points:
        report.notes.append(f"{dup_points} pontos de sinal duplicados (measurement_id + scan_index repetidos).")

    report.signal_rows = len(signal_df)

    if metadata_df.empty:
        report.notes.append(
            "Nenhum arquivo de METADATA encontrado - measurements seguem sem contamination_status/qc_flag."
        )
        merged = signal_df
        merged["contamination_status"] = np.nan
        merged["qc_flag"] = np.nan
        return merged

    metadata_df = metadata_df.copy()
    dup_meta = int(metadata_df.duplicated(subset="measurement_id").sum())
    report.duplicate_metadata_ids = dup_meta
    if dup_meta:
        report.notes.append(f"{dup_meta} measurement_id duplicados em metadata (mantida a primeira ocorrência).")
        metadata_df = metadata_df.drop_duplicates(subset="measurement_id", keep="first")

    if "qc_flag" in metadata_df.columns:
        # conta valores presentes (não nulos) que não pertencem ao conjunto válido
        bad_flags = int(metadata_df["qc_flag"].notna().sum() - metadata_df["qc_flag"].isin(VALID_QC_FLAGS).sum())
        report.invalid_qc_flags = bad_flags
        if bad_flags:
            report.notes.append(f"{bad_flags} valores de qc_flag fora de {sorted(VALID_QC_FLAGS)}.")

    report.metadata_rows = len(metadata_df)

    meta_cols = ["measurement_id"] + [c for c in ROLE_OPTIONAL_COLUMNS["metadata"] if c in metadata_df.columns]
    meta_cols += [c for c in ["contamination_status"] if c in metadata_df.columns and c not in meta_cols]

    merged = signal_df.merge(
        metadata_df[meta_cols], on="measurement_id", how="left", suffixes=("", "_meta")
    )

    # conta measurement_id distintos sem metadata correspondente (não pontos individuais)
    without_meta_ids = int(
        merged.loc[merged["contamination_status"].isna(), "measurement_id"].nunique()
        if "contamination_status" in merged
        else merged["measurement_id"].nunique()
    )
    report.measurements_without_metadata = without_meta_ids
    if without_meta_ids:
        report.notes.append(
            f"{without_meta_ids} measurement_id do arquivo de sinal não encontraram par em metadata."
        )

    meta_ids = set(metadata_df["measurement_id"])
    signal_ids = set(signal_df["measurement_id"])
    orphan_meta = meta_ids - signal_ids
    report.metadata_without_signal = len(orphan_meta)
    if orphan_meta:
        report.notes.append(f"{len(orphan_meta)} measurement_id em metadata não têm sinal correspondente.")

    return merged


def build_prepared_samples(measurements_df: pd.DataFrame, plating_df: pd.DataFrame, report: PreparationReport) -> pd.DataFrame:
    sample_col = "sample_id"
    if sample_col not in measurements_df.columns:
        raise ValueError("Coluna 'sample_id' ausente após a junção de sinal+metadata.")

    base_cols = [c for c in [
        "sample_id", "target_bacterium", "contamination_status", "sensor_lot",
        "experimental_batch", "sample_mean_cfu_ml", "sample_log10_mean_cfu_ml",
    ] if c in measurements_df.columns]

    samples = measurements_df[base_cols].drop_duplicates(subset="sample_id").reset_index(drop=True)

    if plating_df.empty:
        report.notes.append("Nenhum arquivo de PLATING encontrado - amostras seguem sem CFU de referência.")
        samples["plating_cfu_ml_mean"] = np.nan
        samples["plating_log10_cfu_ml_mean"] = np.nan
        report.samples_without_plating = len(samples)
        return samples

    report.plating_rows = len(plating_df)

    agg = (
        plating_df.groupby("sample_id")
        .agg(
            plating_cfu_ml_mean=("calculated_cfu_ml", "mean") if "calculated_cfu_ml" in plating_df.columns else ("colony_count", "mean"),
            plating_log10_cfu_ml_mean=("log10_cfu_ml", "mean") if "log10_cfu_ml" in plating_df.columns else ("colony_count", "mean"),
            plating_replicate_count=("colony_count", "count"),
        )
        .reset_index()
    )

    samples = samples.merge(agg, on="sample_id", how="left")
    without_plating = int(samples["plating_replicate_count"].isna().sum())
    report.samples_without_plating = without_plating
    if without_plating:
        report.notes.append(f"{without_plating} amostras sem nenhum registro de plaqueamento correspondente.")

    plating_only = set(plating_df["sample_id"]) - set(samples["sample_id"])
    if plating_only:
        report.notes.append(f"{len(plating_only)} sample_id em plaqueamento não aparecem nas medições de sinal.")

    return samples


def prepare(input_dir: str | Path, output_dir: str | Path) -> dict[str, pd.DataFrame]:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    report = PreparationReport()

    buckets = discover_and_classify(input_dir, report)
    signal_df = _concat(buckets["signal"])
    metadata_df = _concat(buckets["metadata"])
    plating_df = _concat(buckets["plating"])

    measurements = build_prepared_measurements(signal_df, metadata_df, report)
    samples = build_prepared_samples(measurements, plating_df, report)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    measurements.to_csv(out / "prepared_measurements.csv", index=False)
    samples.to_csv(out / "prepared_samples.csv", index=False)
    report.to_dataframe().to_csv(out / "preparation_report.csv", index=False)

    logger.info("Arquivos classificados: %s", report.files_classified)
    if report.files_unclassified:
        logger.warning("Arquivos ignorados (schema não reconhecido): %s", report.files_unclassified)
    logger.info("prepared_measurements.csv: %d linhas", len(measurements))
    logger.info("prepared_samples.csv: %d linhas", len(samples))
    logger.info("Relatório completo em preparation_report.csv")

    return {"measurements": measurements, "samples": samples, "report": report.to_dataframe()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Arruma e junta os dados brutos em tabelas canônicas.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Diretório com os arquivos brutos (.csv/.txt/.xlsx/.xls).")
    parser.add_argument("--output-dir", type=Path, default=Path("prepared"), help="Diretório de saída para os arquivos preparados.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    prepare(args.input_dir, args.output_dir)


if __name__ == "__main__":
    main()
