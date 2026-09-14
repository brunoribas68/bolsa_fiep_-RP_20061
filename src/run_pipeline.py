"""
run_pipeline.py
=================

CLI único que roda as 3 etapas do pipeline em sequência:

    1) data_preparation.prepare()        -> arruma/junta/valida os dados brutos
    2) ingest_pipeline.run()             -> features, modelos baseline, exportação
    3) advanced_modeling.run()           -> melhoria (diferença entre estágios), opcional

Uso:
    python run_pipeline.py --input-dir Dados --output-dir .

    # pular a etapa 3 (mais lenta, treina 5 modelos x N seeds):
    python run_pipeline.py --input-dir Dados --output-dir . --skip-advanced

Saídas (relativas a --output-dir):
    prepared/            <- etapa 1
    outputs/              <- etapa 2 (banco de dados estruturado baseline)
    outputs_advanced/     <- etapa 3 (melhoria testada)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from data_preparation import prepare  # noqa: E402
from ingest_pipeline import run as run_ingest_pipeline  # noqa: E402
from advanced_modeling import run as run_advanced_modeling  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Roda o pipeline completo (3 etapas) de ponta a ponta.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Pasta com os 3 arquivos brutos (ex.: Dados/).")
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="Pasta-base onde prepared/, outputs/ e outputs_advanced/ serão criadas.")
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--keep-flags", nargs="+", default=["PASS"])
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(10)), help="Seeds usadas na etapa 3 (multi-seed CV).")
    parser.add_argument("--skip-advanced", action="store_true", help="Pula a etapa 3 (mais lenta).")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    keep_flags = tuple(args.keep_flags)

    prepared_dir = args.output_dir / "prepared"
    outputs_dir = args.output_dir / "outputs"
    outputs_advanced_dir = args.output_dir / "outputs_advanced"

    t0 = time.time()
    print(f"\n[1/3] Preparando dados de {args.input_dir} -> {prepared_dir}")
    prepare(args.input_dir, prepared_dir)

    print(f"\n[2/3] Ingerindo (features + modelos baseline) -> {outputs_dir}")
    ingest_result = run_ingest_pipeline(prepared_dir, outputs_dir, random_state=args.random_state, keep_flags=keep_flags)
    if ingest_result["model_metrics"] is not None:
        print(ingest_result["model_metrics"][["model", "test_balanced_accuracy"]].to_string(index=False))
    else:
        print("Dados insuficientes para modelagem baseline com o filtro atual.")

    if not args.skip_advanced:
        print(f"\n[3/3] Melhoria (diferença entre estágios) -> {outputs_advanced_dir}")
        summary = run_advanced_modeling(prepared_dir, outputs_advanced_dir, seeds=args.seeds, keep_flags=keep_flags)
        print(summary.to_string(index=False))
    else:
        print("\n[3/3] Pulado (--skip-advanced)")

    print(f"\nPipeline concluído em {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
