"""Linha de comando da pipeline FIEP.

    python -m fiep ingerir --entrada Dados --saida dados/processados
    python -m fiep qc      --dados dados/processados
    python -m fiep treinar --dados dados/processados [--config configs/default.toml]
    python -m fiep prever  --entrada nova_coleta/ [--modelo modelos] --saida resultado.csv
    python -m fiep tudo    --entrada Dados          # ingerir + treinar

Depois de `pip install -e .`, o mesmo vale como `fiep <comando> ...`.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config


def _ingerir(a):
    from .ingest import ingerir
    ds = ingerir(a.entrada)
    ds.salvar(a.saida)
    print(f"{len(ds.medicoes)} medições, {len(ds.amostras)} amostras -> {a.saida}")
    if len(ds.relatorio[ds.relatorio.tipo == "aviso"]):
        print("Avisos:\n  " + "\n  ".join(ds.relatorio.loc[ds.relatorio.tipo == "aviso", "detalhe"]))
    return ds


def _qc(a):
    from .ingest import Dataset
    from .qc import avaliar
    ds = Dataset.carregar(a.dados)
    qc = avaliar(ds.medicoes, ds.pontos, load_config(a.config))
    destino = Path(a.dados) / "qc.csv"
    qc.to_csv(destino, index=False)
    print(qc["qc_final"].value_counts().to_string())
    ruins = qc[qc["qc_final"] != "PASS"]
    if len(ruins):
        print("\nReprovadas/em revisão:")
        print(ruins[["measurement_id", "qc_final", "qc_motivos"]].head(30).to_string(index=False))
    print(f"\nDetalhes em {destino}")


def _treinar(a, ds=None):
    from .ingest import Dataset
    from .model import treinar
    ds = ds or Dataset.carregar(a.dados)
    r = treinar(ds, load_config(a.config), a.modelos)
    print(r["metricas"][["modelo", "balanced_accuracy", "sensibilidade", "especificidade", "roc_auc",
                         "limiar"]].round(3).to_string(index=False))
    print(f"\nModelo escolhido: {r['cartao']['modelo']} -> {r['pasta']}")


def _prever(a):
    from .model import carregar
    from .predict import prever
    pacote = carregar(a.modelo)
    res = prever(a.entrada, pacote)
    print(res.drop(columns=["measurement_id"], errors="ignore").to_string(index=False))
    if a.saida:
        res.to_csv(a.saida, index=False)
        print(f"\nSalvo em {a.saida}")


def _tudo(a):
    a.saida = a.dados
    ds = _ingerir(a)
    _treinar(a, ds)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fiep", description="Pipeline FIEP: voltametria -> contaminação")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingerir", help="lê .nox/tabelas e grava o formato canônico")
    p.add_argument("--entrada", required=True)
    p.add_argument("--saida", default="dados/processados")
    p.set_defaults(fn=_ingerir)

    p = sub.add_parser("qc", help="controle de qualidade das medições ingeridas")
    p.add_argument("--dados", default="dados/processados")
    p.add_argument("--config")
    p.set_defaults(fn=_qc)

    p = sub.add_parser("treinar", help="valida (CV agrupada), escolhe e salva o modelo")
    p.add_argument("--dados", default="dados/processados")
    p.add_argument("--config")
    p.add_argument("--modelos", default="modelos")
    p.set_defaults(fn=_treinar)

    p = sub.add_parser("prever", help="classifica medições novas com o modelo salvo")
    p.add_argument("--entrada", required=True, help="pasta com .nox + planilha de metadados, ou tabelas")
    p.add_argument("--modelo", default="modelos", help="pasta de modelos (usa ATUAL) ou pasta/arquivo de um modelo")
    p.add_argument("--saida")
    p.set_defaults(fn=_prever)

    p = sub.add_parser("tudo", help="ingerir + treinar")
    p.add_argument("--entrada", required=True)
    p.add_argument("--dados", default="dados/processados")
    p.add_argument("--config")
    p.add_argument("--modelos", default="modelos")
    p.set_defaults(fn=_tudo)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        a.fn(a)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
