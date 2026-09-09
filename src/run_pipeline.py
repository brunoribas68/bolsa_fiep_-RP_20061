from __future__ import annotations

import argparse
from pathlib import Path

from biosensor_pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline para organização, validação e modelagem de sinais eletroquímicos de biossensores."
    )
    parser.add_argument("--input-dir", type=Path, required=True, help="Diretório com arquivos brutos de voltametria.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="Diretório para resultados processados.")
    parser.add_argument("--random-state", type=int, default=42, help="Semente aleatória para modelagem.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    result = run_pipeline(args.input_dir, args.output_dir, random_state=args.random_state)

    print("Pipeline executado com sucesso.")
    print(f"Medições processadas: {result['long']['measurement_uid'].nunique()}")
    print(f"Amostras: {result['long']['sample_uid'].nunique()}")
    if result["model_metrics"] is not None:
        print("Modelos avaliados:")
        print(result["model_metrics"][["model", "test_balanced_accuracy"]].to_string(index=False))
    else:
        print("Dados insuficientes para modelagem supervisionada (é necessário mais de 1 classe e ao menos 8 medições).")


if __name__ == "__main__":
    main()
