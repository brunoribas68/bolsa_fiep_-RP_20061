"""Linha de comando da pipeline FIEP (`fiep <comando>` ou `python -m fiep <comando>`).

Fluxo principal:
    fiep planilha    --entrada dados/empresa1          # planilha de metadados do lote de .nox
    fiep db importar --entrada dados                   # grava no banco (dados/fiep.db) e roda o QC
    fiep experimento --artigo                         # divide dados/ em 50/25/25 (+ pastas)
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
import os
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
    from .predict import resumo_por_amostra
    pacote = carregar(a.modelo)
    res = prever(a.entrada, pacote, niveis=load_config(a.config).get("niveis"))
    am = resumo_por_amostra(res)
    if getattr(a, "db", None):
        from . import db
        con = db.conectar(a.db)
        n = db.gravar_predicoes(con, res, pacote["cartao"], a.modelo)
        print(f"{n} previsões gravadas em {a.db} (modelo {pacote['cartao']['id']}).")
    if len(am):
        print("Por amostra:")
        print(am.to_string(index=False))
        print("\nPor réplica:")
    print(res.drop(columns=["measurement_id"], errors="ignore").to_string(index=False))
    if a.saida:
        res.to_csv(a.saida, index=False)
        destino_am = Path(a.saida).with_name(Path(a.saida).stem + "_amostras.csv")
        am.to_csv(destino_am, index=False)
        print(f"\nSalvo em {a.saida} e {destino_am}")


def _experimento(a):
    import shutil
    from .divisao import CONJUNTOS, de_pastas, montar, subconjunto
    from .experimentos import rodar
    cfg = load_config(a.config)
    if a.db:
        from . import db
        con = db.conectar(a.db)
        todos = db.carregar(con, a.filtro)
        med = todos.medicoes
        # conjunto definido na importação (pastas treino/validacao/teste) e/ou por filtro SQL
        ids = {k: set(med.loc[med["conjunto"] == k, "sample_id"]) if "conjunto" in med else set()
               for k in CONJUNTOS}
        for k in CONJUNTOS:
            if getattr(a, f"filtro_{k}"):
                ids[k] |= set(db.carregar(con, getattr(a, f"filtro_{k}")).medicoes["sample_id"])
        fixos = {k: subconjunto(todos, v) for k, v in ids.items() if v}
        ja = set().union(*ids.values())
        div = montar(subconjunto(todos, set(med["sample_id"].dropna()) - ja), fixos, cfg)
    else:
        div = de_pastas(a.dados, cfg)
    print(div.descricao())
    r = rodar(div, cfg, saida=a.saida, pasta_modelos=a.modelos, rapido=a.rapido)
    cols = ["posicao", "variante", "modelo", "cv_balanced_accuracy", "cv_ba_desvio", "val_balanced_accuracy",
            "val_roc_auc", "teste_balanced_accuracy", "teste_roc_auc"]
    print(f"\nTop 10 (ordenado por: {r['resumo']['criterio_escolha']}):")
    print(r["placar"][[c for c in cols if c in r["placar"]]].head(10).round(3).to_string(index=False))
    if len(r["regressao"]):
        print("\nRegressão da carga (log10 UFC/mL, contaminadas):")
        print(r["regressao"].round(3).to_string(index=False))
    res = r["resumo"]
    ta = res.get("teste_por_amostra")
    if ta:
        print(f"\nTeste por amostra ({ta['n_amostras']} amostras, média das réplicas): "
              f"AB {ta['balanced_accuracy']:.3f} | sensibilidade {ta['sensibilidade']:.3f} | "
              f"especificidade {ta['especificidade']:.3f}")
    if res.get("teste_niveis"):
        tn = res["teste_niveis"]
        print(f"Níveis de contaminação no teste: acurácia {tn['acuracia']:.3f} (AB {tn['balanced_accuracy']:.3f}); "
              f"matriz em {r['pasta']}/niveis_teste.csv")
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
        os.environ["FIEP_DB_URL"] = a.db
    if not (raiz / "web" / "dist" / "index.html").exists():
        print("Frontend ainda não compilado: cd web && npm install && npm run build (a API funciona em /docs).")
    print(f"Abra http://{a.host}:{a.porta} no navegador (Ctrl+C para parar)")
    uvicorn.run("api.app:app", host=a.host, port=a.porta, reload=False)


def _excel(a):
    from .excel import converter_pasta
    gerados = converter_pasta(a.entrada, a.saida, refazer=a.refazer)
    print(f"{len(gerados)} arquivo(s) convertido(s)" + (f" em {gerados[0].parent}" if gerados else " (já estavam em dia)"))


def _planilha(a):
    import pandas as pd
    from .planilha import gerar_planilha
    cfg = load_config(a.config)
    destino, n = gerar_planilha(a.entrada, cfg=cfg)
    print(f"{n} arquivo(s) novo(s) em {destino} (amostra, réplica, estágio e data já deduzidos — só confira)")
    am_path = Path(a.entrada) / "amostras.csv"
    if not am_path.exists():
        print("Nenhuma amostra deduzida (há .nox na pasta?).")
        return
    am = pd.read_csv(am_path, dtype=str, encoding="utf-8-sig").fillna("")
    faltam = am[am["contamination_status"].str.strip() == ""]
    print(f"\n{am_path}: {len(am)} amostra(s), uma linha por amostra")
    print(am.drop(columns=["surface_type"], errors="ignore").to_string(index=False, max_rows=30))
    if len(faltam):
        print(f"\nPreencha contamination_status (1 = contaminada, 0 = não; do plaqueamento) e, se houver, "
              f"sample_log10_mean_cfu_ml nas {len(faltam)} linha(s) de {am_path}.")
        print("Dica: pastas chamadas contaminada/ e nao_contaminada/ (ou positivo/negativo) já preenchem o rótulo.")
    print("Depois:\n  fiep db importar --entrada dados\n  fiep experimento --artigo")


def _usuario(a):
    import getpass

    from . import db, usuarios
    from .orm import Usuario
    # conta é coisa da plataforma: banco novo já vem com os dados de exemplo (FIEP_DADOS_EXEMPLO=0 para não)
    s = db.conectar(a.db, dados_exemplo=os.environ.get("FIEP_DADOS_EXEMPLO", "1") == "1")
    if a.acao == "listar":
        for u in s.query(Usuario).order_by(Usuario.email):
            print(f"{u.email:35s} {u.nome:25s} {u.papel:12s} {'ativo' if u.ativo else 'DESATIVADO'}")
        return
    if not a.email:
        raise ValueError("informe --email")
    senha = None
    if a.acao in ("criar", "senha"):
        senha = os.environ.get("FIEP_SENHA_NOVA") or getpass.getpass("Senha: ")
        if not os.environ.get("FIEP_SENHA_NOVA") and getpass.getpass("Repita a senha: ") != senha:
            raise ValueError("as senhas não conferem")
    if a.acao == "criar":
        u = usuarios.criar(s, a.email, a.nome or a.email.split("@")[0], senha, a.papel, a.instituicao)
        print(f"Usuário {u.email} criado ({u.papel}).")
        return
    u = usuarios.por_email(s, a.email)
    if u is None:
        raise ValueError(f"usuário {a.email} não encontrado")
    if a.acao == "senha":
        usuarios.trocar_senha(s, u, senha)
        u.ativo = True
        s.commit()
        print(f"Senha de {u.email} redefinida.")
    elif a.acao == "desativar":
        u.ativo, u.versao_sessao = False, u.versao_sessao + 1
        s.commit()
        print(f"{u.email} desativado.")


def _db(a):
    from . import db
    if a.acao == "migrar":
        con = db.conectar(a.db, dados_exemplo=not a.sem_exemplo)
        print("Banco atualizado (migrations aplicadas).")
        print(db.resumo(con).to_string(index=False))
        return
    con = db.conectar(a.db)
    if a.acao == "exemplo":
        if a.remover:
            print("Dados de exemplo removidos." if db.remover_exemplo(con) else "Não há dados de exemplo no banco.")
        else:
            r = db.carregar_exemplo(con)
            print(f"Dados de exemplo carregados: {r['amostras']} amostras, {r['medicoes']} medições." if r
                  else "Os dados de exemplo já estão no banco.")
        return
    if a.acao == "importar":
        if not a.entrada:
            raise ValueError("informe a pasta com --entrada")
        from .divisao import CONJUNTOS, RESERVADAS
        from .ingest import ingerir, tem_dados
        from .qc import avaliar
        base = Path(a.entrada)
        # pasta de dados com treino/validacao/teste: cada parte é gravada com o seu conjunto
        partes = [(None, base, RESERVADAS)] if tem_dados(base, RESERVADAS) else []
        partes += [(k, base / k, ()) for k in CONJUNTOS if tem_dados(base / k)]
        if not partes and tem_dados(base / "exemplo_case"):
            print(f"Sem dados em {base}: importando {base / 'exemplo_case'} (demonstração).")
            partes = [(None, base / "exemplo_case", ())]
        if not partes:
            raise FileNotFoundError(f"Nenhum dado em {base}")
        if a.conjunto:
            partes = [(a.conjunto, p, ex) for _, p, ex in partes]
        if not a.sem_excel:                 # cópia em Excel (formato NOVA) de cada .nox, em dados/excel/
            from .excel import converter_pasta
            n = sum(len(converter_pasta(p)) for _, p, _ in partes if p.name != "exemplo_case"
                    and any(p.rglob("*.nox")))
            if n:
                print(f"{n} .nox convertido(s) para Excel em dados/excel/")
        for conjunto, pasta, excluir in partes:
            ds = ingerir(pasta, excluir=excluir)
            ds.medicoes["conjunto"] = conjunto
            r = db.importar(con, ds, origem=str(pasta), conjunto=conjunto, empresa=a.empresa)
            n_qc = db.gravar_qc(con, avaliar(ds.medicoes, ds.pontos, load_config(a.config)))
            print(f"Importação #{r['importacao_id']} ({pasta}, conjunto: {conjunto or 'a sortear'}): "
                  f"{r['medicoes']} medições, {r['pontos']:,} pontos, {r['amostras']} amostras, "
                  f"{r['arquivos_novos']} arquivo(s) novo(s); QC de {n_qc} medições.")
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
        df = db.sql(con, a.consulta)
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
    p.add_argument("--config", help="configuração com os [niveis] de contaminação (padrão: a do modelo)")
    p.set_defaults(fn=_prever)

    p = sub.add_parser("experimento", help="compara variantes de features x modelos e registra o melhor")
    p.add_argument("--dados", default="dados",
                   help="pasta de dados: o que estiver solto é dividido em treino/validação/teste (padrão 50/25/25); "
                        "o que estiver em dados/treino, dados/validacao e dados/teste é somado ao conjunto da pasta")
    p.add_argument("--db", help="usar o banco SQLite em vez das pastas")
    p.add_argument("--filtro", help="filtro SQL dos dados a dividir (com --db)")
    p.add_argument("--filtro-treino", help="filtro SQL de amostras que vão inteiras para o treino (com --db)")
    p.add_argument("--filtro-validacao", help="idem, para a validação (com --db)")
    p.add_argument("--filtro-teste", help="idem, para o teste (ex.: outra empresa) (com --db)")
    p.add_argument("--config")
    p.add_argument("--saida", default="resultados")
    p.add_argument("--modelos", default="modelos")
    p.add_argument("--rapido", action="store_true", help="menos variantes e modelos (para testar)")
    p.add_argument("--artigo", action="store_true", help="copiar figuras e tabelas para o artigo")
    p.add_argument("--artigo-pasta", default="artigo/gerado")
    p.set_defaults(fn=_experimento)

    p = sub.add_parser("servir", help="abre a plataforma (frontend + API, com login)")
    p.add_argument("--modelos", default="modelos")
    p.add_argument("--db", help="arquivo SQLite ou URL do banco (padrão: FIEP_DB_URL ou dados/fiep.db)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--porta", type=int, default=8000)
    p.set_defaults(fn=_servir)

    p = sub.add_parser("planilha", help="cria/completa a planilha de metadados de um lote de .nox")
    p.add_argument("--entrada", required=True, help="pasta com os .nox (ex.: dados/treino)")
    p.add_argument("--config")
    p.set_defaults(fn=_planilha)

    p = sub.add_parser("excel", help="converte os .nox de uma pasta para Excel (formato do NOVA)")
    p.add_argument("--entrada", required=True, help="pasta com .nox (ex.: dados/empresa1)")
    p.add_argument("--saida", help="pasta de saída (padrão: dados/excel/<lote>)")
    p.add_argument("--refazer", action="store_true", help="converte de novo mesmo se o Excel já existir")
    p.set_defaults(fn=_excel)

    p = sub.add_parser("usuario", help="contas da plataforma: criar, listar, senha, desativar")
    p.add_argument("acao", choices=["criar", "listar", "senha", "desativar"])
    p.add_argument("--email")
    p.add_argument("--nome")
    p.add_argument("--papel", choices=["admin", "colaborador", "leitor"], default="colaborador")
    p.add_argument("--instituicao")
    p.add_argument("--db", help="arquivo SQLite ou URL do banco (padrão: FIEP_DB_URL ou dados/fiep.db)")
    p.set_defaults(fn=_usuario)

    p = sub.add_parser("db", help="banco de dados: migrar, importar, resumo, exportar, sql, exemplo")
    p.add_argument("acao", choices=["migrar", "importar", "resumo", "exportar", "sql", "exemplo"])
    p.add_argument("consulta", nargs="?", help="consulta SQL (para a ação sql)")
    p.add_argument("--db", help="arquivo SQLite ou URL do banco (padrão: FIEP_DB_URL ou dados/fiep.db)")
    p.add_argument("--sem-exemplo", action="store_true", help="migrar: não carregar os dados de exemplo")
    p.add_argument("--remover", action="store_true", help="exemplo: apagar os dados de exemplo")
    p.add_argument("--empresa", help="importar: nome da empresa dos dados")
    p.add_argument("--entrada", help="pasta com .nox/tabelas (para importar); com dados/, as subpastas "
                                     "treino/validacao/teste são gravadas com o seu conjunto")
    p.add_argument("--sem-excel", action="store_true", help="não gerar a cópia em Excel dos .nox (dados/excel/)")
    p.add_argument("--conjunto", choices=["treino", "validacao", "teste"],
                   help="grava tudo o que for importado como deste conjunto")
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
