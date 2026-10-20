"""Linha de comando da pipeline FIEP (`fiep <comando>` ou `python -m fiep <comando>`).

Fluxo principal:
    fiep planilha    --entrada dados/treino            # planilha de metadados do lote de .nox
    fiep db importar --entrada dados/treino            # grava no banco (dados/fiep.db) e roda o QC
    fiep experimento --treino dados/treino --validacao dados/validacao --artigo
    fiep servir                                        # página web + API com o modelo registrado
    fiep prever      --entrada nova_coleta/ --db dados/fiep.db

Banco:
    fiep db resumo | fiep db sql "SELECT ..." | fiep db exportar --saida dados/fiep_banco.xlsx

Treino simples (sem comparar variantes) e fluxo só com arquivos:
    fiep treinar --db dados/fiep.db
    fiep ingerir --entrada dados/treino --saida dados/processados
    fiep qc      --dados dados/processados
    fiep tudo    --entrada dados/treino
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


def _experimento(a):
    import shutil
    from .experimentos import rodar
    from .ingest import ingerir
    cfg = load_config(a.config)
    if a.db:
        from . import db
        con = db.conectar(a.db)
        ds = db.carregar(con, a.filtro)
        ds_val = db.carregar(con, a.filtro_validacao) if a.filtro_validacao else None
        if ds_val is not None:          # o que é validação não entra no treino
            ids = set(ds_val.medicoes["sample_id"])
            from .experimentos import subconjunto
            ds = subconjunto(ds, set(ds.medicoes["sample_id"]) - ids)
    else:
        ds = ingerir(a.treino)
        ds_val = ingerir(a.validacao) if a.validacao and _tem_dados(a.validacao) else None
    print(f"Treino: {ds.medicoes['sample_id'].nunique()} amostras | "
          f"validação externa: {'sim, ' + str(ds_val.medicoes['sample_id'].nunique()) + ' amostras' if ds_val is not None else 'não (teste = 20% separado)'}")
    r = rodar(ds, cfg, ds_val, saida=a.saida, pasta_modelos=a.modelos, rapido=a.rapido)
    cols = ["posicao", "variante", "modelo", "cv_balanced_accuracy", "cv_ba_desvio", "cv_roc_auc",
            "teste_balanced_accuracy", "teste_roc_auc"]
    print("\nTop 10 (ordenado pela validação cruzada no treino):")
    print(r["placar"][[c for c in cols if c in r["placar"]]].head(10).round(3).to_string(index=False))
    if len(r["regressao"]):
        print("\nRegressão da carga (log10 UFC/mL, contaminadas):")
        print(r["regressao"].round(3).to_string(index=False))
    res = r["resumo"]
    if res.get("formula_sisso"):
        print(f"\nSISSO: {res['formula_sisso']}")
    print(f"\nResultados em {r['pasta']}" + (f" | modelo registrado: {res.get('modelo_registrado')}" if res.get("modelo_registrado") else ""))
    if a.artigo:
        destino = Path(a.artigo_pasta)
        for sub in ("figuras", "tabelas"):
            (destino / sub).mkdir(parents=True, exist_ok=True)
            for f in (r["pasta"] / sub).glob("*"):
                shutil.copy2(f, destino / sub / f.name)
        print(f"Figuras e tabelas copiadas para {destino}/")


def _tem_dados(pasta) -> bool:
    p = Path(pasta)
    return p.exists() and any(x.suffix.lower() in {".nox", ".csv", ".xlsx"} for x in p.rglob("*"))


def _servir(a):
    import os
    try:
        import uvicorn
    except ImportError:
        raise ValueError('instale as dependências da API: pip install -e ".[api]"')
    raiz = Path(__file__).resolve().parents[1]
    if not (raiz / "api" / "app.py").exists():
        raise FileNotFoundError("pasta api/ não encontrada: rode a partir do repositório do projeto")
    sys.path.insert(0, str(raiz))
    os.environ.setdefault("FIEP_MODELOS", str(Path(a.modelos).resolve()))
    if a.db:
        os.environ["FIEP_DB"] = str(Path(a.db).resolve())
    print(f"Abra http://{a.host}:{a.porta} no navegador (Ctrl+C para parar)")
    uvicorn.run("api.app:app", host=a.host, port=a.porta, reload=False)


def _planilha(a):
    from .planilha import gerar_planilha
    destino, n = gerar_planilha(a.entrada, cfg=load_config(a.config))
    print(f"{n} arquivo(s) novo(s) adicionados em {destino}")
    print("Preencha sample_id, replicate_id, sensor_state e contamination_status e depois rode:")
    print(f"  fiep db importar --entrada {a.entrada}")


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

    p = sub.add_parser("experimento", help="compara variantes de features x modelos e registra o melhor")
    p.add_argument("--treino", default="dados/treino", help="pasta de treino (.nox + planilha e/ou tabelas)")
    p.add_argument("--validacao", default="dados/validacao", help="validação externa (opcional; vazia = 20%% separado)")
    p.add_argument("--db", help="usar o banco SQLite em vez das pastas")
    p.add_argument("--filtro", help="filtro SQL do treino (com --db)")
    p.add_argument("--filtro-validacao", help="filtro SQL que define a validação externa (com --db)")
    p.add_argument("--config")
    p.add_argument("--saida", default="resultados")
    p.add_argument("--modelos", default="modelos")
    p.add_argument("--rapido", action="store_true", help="menos variantes e modelos (para testar)")
    p.add_argument("--artigo", action="store_true", help="copiar figuras e tabelas para o artigo")
    p.add_argument("--artigo-pasta", default="artigo/gerado")
    p.set_defaults(fn=_experimento)

    p = sub.add_parser("servir", help="abre a página web e a API de previsão")
    p.add_argument("--modelos", default="modelos")
    p.add_argument("--db", help="gravar as previsões feitas pela página neste banco")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=8000)
    p.set_defaults(fn=_servir)

    p = sub.add_parser("planilha", help="cria/completa a planilha de metadados de um lote de .nox")
    p.add_argument("--entrada", required=True, help="pasta com os .nox (ex.: dados/treino)")
    p.add_argument("--config")
    p.set_defaults(fn=_planilha)

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
