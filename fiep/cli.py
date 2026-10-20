"""Linha de comando da pipeline FIEP.

Banco de dados (SQLite, padrão dados/fiep.db):
    python -m fiep db importar --entrada Dados          # lê .nox/tabelas, grava no banco e roda o QC
    python -m fiep db resumo
    python -m fiep db exportar --saida banco.xlsx       # ou --formato csv --saida pasta/
    python -m fiep db sql "SELECT * FROM v_replicatas LIMIT 10"
    python -m fiep treinar --db dados/fiep.db [--filtro "tecnica = 'DPV'"]
    python -m fiep prever  --entrada nova_coleta/ --db dados/fiep.db   # grava as previsões no banco

Sem banco (arquivos CSV):
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
    con = None
    if getattr(a, "db", None):
        from . import db
        con = db.conectar(a.db)
        ds = ds or db.carregar(con, a.filtro)
        print(f"{len(ds.medicoes)} medições lidas de {a.db}" + (f" (filtro: {a.filtro})" if a.filtro else ""))
    ds = ds or Dataset.carregar(a.dados)
    r = treinar(ds, load_config(a.config), a.modelos)
    if con is not None:
        from . import db
        from .qc import avaliar
        db.registrar_modelo(con, r["cartao"], r["pasta"])
        db.gravar_qc(con, avaliar(ds.medicoes, ds.pontos, load_config(a.config)))
        print(f"Modelo {r['cartao']['id']} registrado no banco.")
    print(r["metricas"][["modelo", "balanced_accuracy", "sensibilidade", "especificidade", "roc_auc",
                         "limiar"]].round(3).to_string(index=False))
    print(f"\nModelo escolhido: {r['cartao']['modelo']} -> {r['pasta']}")


def _prever(a):
    from .model import carregar
    from .predict import prever
    pacote = carregar(a.modelo)
    res = prever(a.entrada, pacote)
    if getattr(a, "db", None):
        from . import db
        con = db.conectar(a.db)
        n = db.gravar_predicoes(con, res, pacote["cartao"], a.modelo)
        print(f"{n} previsões gravadas em {a.db} (modelo {pacote['cartao']['id']}).")
    print(res.drop(columns=["measurement_id"], errors="ignore").to_string(index=False))
    if a.saida:
        res.to_csv(a.saida, index=False)
        print(f"\nSalvo em {a.saida}")


def _db(a):
    import pandas as pd
    from . import db
    con = db.conectar(a.db)
    if a.acao == "importar":
        if not a.entrada:
            raise ValueError("informe a pasta com --entrada")
        from .ingest import ingerir
        from .qc import avaliar
        ds = ingerir(a.entrada)
        r = db.importar(con, ds, origem=a.entrada)
        n_qc = db.gravar_qc(con, avaliar(ds.medicoes, ds.pontos, load_config(a.config)))
        print(f"Importação #{r['importacao_id']}: {r['medicoes']} medições, {r['pontos']:,} pontos, "
              f"{r['amostras']} amostras, {r['arquivos_novos']} arquivo(s) novo(s); QC de {n_qc} medições.")
        avisos = ds.relatorio.loc[ds.relatorio.tipo == "aviso", "detalhe"]
        if len(avisos):
            print("Avisos:\n  " + "\n  ".join(avisos))
        print()
        print(db.resumo(con).to_string(index=False))
    elif a.acao == "resumo":
        print(db.resumo(con).to_string(index=False))
    elif a.acao == "exportar":
        destino = a.saida or ("dados/exportacao" if a.formato == "csv" else "dados/fiep_banco.xlsx")
        for g in db.exportar(con, destino, a.formato):
            print("gerado:", g)
    elif a.acao == "sql":
        if not a.consulta:
            raise ValueError('informe a consulta, ex.: fiep db sql "SELECT * FROM v_replicatas LIMIT 5"')
        df = pd.read_sql(a.consulta, con)
        print(df.to_string(index=False, max_rows=60))
        if a.saida:
            df.to_csv(a.saida, index=False)
            print(f"\n{len(df)} linhas salvas em {a.saida}")


def _tudo(a):
    a.saida = a.dados
    ds = _ingerir(a)
    if a.db:
        from . import db
        db.importar(db.conectar(a.db), ds, origem=a.entrada)
        ds = None                          # treina a partir do banco (com o filtro, se houver)
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
    p.add_argument("--db", help="treinar com os dados do banco SQLite (e registrar o modelo nele)")
    p.add_argument("--filtro", help="filtro SQL sobre a tabela medicoes, ex.: \"tecnica = 'DPV'\"")
    p.add_argument("--config")
    p.add_argument("--modelos", default="modelos")
    p.set_defaults(fn=_treinar)

    p = sub.add_parser("prever", help="classifica medições novas com o modelo salvo")
    p.add_argument("--entrada", required=True, help="pasta com .nox + planilha de metadados, ou tabelas")
    p.add_argument("--modelo", default="modelos", help="pasta de modelos (usa ATUAL) ou pasta/arquivo de um modelo")
    p.add_argument("--saida")
    p.add_argument("--db", help="gravar as previsões neste banco SQLite")
    p.set_defaults(fn=_prever)

    p = sub.add_parser("db", help="banco de dados SQLite: importar, resumo, exportar, sql")
    p.add_argument("acao", choices=["importar", "resumo", "exportar", "sql"])
    p.add_argument("consulta", nargs="?", help="consulta SQL (para a ação sql)")
    p.add_argument("--db", default="dados/fiep.db")
    p.add_argument("--entrada", help="pasta com .nox/tabelas (para importar)")
    p.add_argument("--config")
    p.add_argument("--formato", choices=["xlsx", "csv"], default="xlsx")
    p.add_argument("--saida")
    p.set_defaults(fn=_db)

    p = sub.add_parser("tudo", help="ingerir + treinar")
    p.add_argument("--entrada", required=True)
    p.add_argument("--dados", default="dados/processados")
    p.add_argument("--config")
    p.add_argument("--modelos", default="modelos")
    p.add_argument("--db", help="também importar para este banco e treinar a partir dele")
    p.add_argument("--filtro")
    p.set_defaults(fn=_tudo)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        a.fn(a)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
