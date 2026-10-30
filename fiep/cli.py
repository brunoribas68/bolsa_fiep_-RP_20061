"""Linha de comando do projeto FIEP (`fiep <comando>` ou `python -m fiep <comando>`).

Ajuda: `fiep -h` e `fiep <comando> -h`. Todas as opções: docs/COMANDOS.md (gerado por `fiep docs`).
O parser fica em `construir_parser()`; o README e docs/COMANDOS.md são conferidos pelos testes
(tests/test_docs.py), então um comando novo precisa aparecer no README.
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
    qc = avaliar(ds.medicoes, ds.pontos, _cfg(a))
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
    r = treinar(ds, _cfg(a), a.modelos)
    if con is not None:
        from . import db
        from .qc import avaliar
        db.registrar_modelo(con, r["cartao"], r["pasta"])
        db.gravar_qc(con, avaliar(ds.medicoes, ds.pontos, _cfg(a)))
        print(f"Modelo {r['cartao']['id']} registrado no banco.")
    print(r["metricas"][["modelo", "balanced_accuracy", "sensibilidade", "especificidade", "roc_auc",
                         "limiar"]].round(3).to_string(index=False))
    print(f"\nModelo escolhido: {r['cartao']['modelo']} -> {r['pasta']}")


def _prever(a):
    from .model import carregar
    from .predict import prever
    from .predict import resumo_por_amostra
    pacote = carregar(a.modelo)
    res = prever(a.entrada, pacote, niveis=_cfg(a).get("niveis"))
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
    from .divisao import CONJUNTOS, de_pastas
    from .experimentos import rodar
    cfg = _cfg(a)
    if a.db:
        from . import db
        from .divisao import de_banco
        con = db.conectar(a.db)
        div, aviso = de_banco(con, cfg, a.filtro, filtros_fixos={k: getattr(a, f"filtro_{k}") for k in CONJUNTOS},
                              com_exemplo=a.com_exemplo)
        if aviso:
            print(aviso)
    else:
        div = de_pastas(a.dados, cfg)
    print(div.descricao())
    lista = lambda t: [x.strip() for x in t.split(",") if x.strip()] if t else None  # noqa: E731
    r = rodar(div, cfg, saida=a.saida, pasta_modelos=a.modelos, rapido=a.rapido, algoritmos=lista(a.algoritmos),
              variantes=lista(a.variantes), ativar=not a.nao_ativar)
    cols = ["posicao", "variante", "modelo", "cv_balanced_accuracy", "cv_ba_desvio", "val_balanced_accuracy",
            "val_roc_auc", "teste_balanced_accuracy", "teste_roc_auc"]
    print(f"\nTop 10 (ordenado por: {r['resumo']['criterio_escolha']}):")
    from .catalogo import nome_classificador, nome_regressor
    from .experimentos import INFO_VARIANTES

    def legivel(t, nome):
        t = t.copy()
        if "modelo" in t:
            t["modelo"] = t["modelo"].map(nome)
        if "variante" in t:
            t["variante"] = t["variante"].map(lambda v: INFO_VARIANTES.get(v, {}).get("nome", v))
        return t.rename(columns={"modelo": "algoritmo", "variante": "representação"})
    print(legivel(r["placar"][[c for c in cols if c in r["placar"]]].head(10).round(3), nome_classificador)
          .to_string(index=False))
    if len(r["regressao"]):
        print("\nRegressão da carga (log10 UFC/mL, contaminadas):")
        print(legivel(r["regressao"].round(3), nome_regressor).to_string(index=False))
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


def estado_frontend(raiz: Path) -> str:
    """'ok', 'ausente' (nunca compilado) ou 'desatualizado' (código da tela mais novo que a compilação)."""
    web = raiz / "web"
    alvo = web / "dist" / "index.html"
    if not alvo.exists():
        return "ausente"
    fontes = [p for p in (web / "src").rglob("*") if p.is_file()] + \
             [web / n for n in ("index.html", "package.json", "vite.config.ts") if (web / n).exists()]
    mais_novo = max((p.stat().st_mtime for p in fontes), default=0)
    return "desatualizado" if mais_novo > alvo.stat().st_mtime + 1 else "ok"


def compilar_frontend(raiz: Path) -> bool:
    """npm install (se preciso) + npm run build. Devolve True se compilou."""
    import shutil
    import subprocess
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    web = raiz / "web"
    if not npm:
        print("  npm não encontrado: instale o Node.js (https://nodejs.org) e rode: cd web; npm install; npm run build")
        return False
    passos = ([[npm, "install"]] if not (web / "node_modules").exists() else []) + [[npm, "run", "build"]]
    for cmd_ in passos:
        print("  $", " ".join(["npm", *cmd_[1:]]))
        r = subprocess.run(cmd_, cwd=web, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print((r.stdout + r.stderr)[-3000:])
            print("  A compilação falhou: a plataforma vai abrir com a versão antiga da tela. "
                  "Mande a mensagem acima para quem cuida do sistema.")
            return False
    print("  Tela compilada.")
    return True


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
    est = estado_frontend(raiz)
    if est != "ok":
        print("A tela (frontend) " + ("ainda não foi compilada." if est == "ausente"
                                      else "está desatualizada: o código mudou depois da última compilação."))
        if a.sem_compilar:
            print("  --sem-compilar: rode cd web; npm install; npm run build")
        else:
            print("  Compilando agora (só desta vez; leva ~1 minuto)...")
            compilar_frontend(raiz)
    print(f"Abra http://{a.host}:{a.porta} no navegador (Ctrl+C para parar)")
    uvicorn.run("api.app:app", host=a.host, port=a.porta, reload=False)


def _excel(a):
    from .excel import converter_pasta
    gerados = converter_pasta(a.entrada, a.saida, refazer=a.refazer)
    print(f"{len(gerados)} arquivo(s) convertido(s)" + (f" em {gerados[0].parent}" if gerados else " (já estavam em dia)"))


def _planilha(a):
    import pandas as pd
    from .planilha import gerar_planilha
    cfg = _cfg(a)
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


def _nome_modelo(s) -> str:
    """'log_reg_C0.1 [dif_curva]' -> 'Regressão logística — regularização forte, C = 0,1 · Curva de diferença entre etapas'."""
    import re
    from .catalogo import nome_classificador
    from .experimentos import INFO_VARIANTES
    m = re.match(r"^(.*?)\s*\[(.+)\]\s*$", str(s or ""))
    if not m:
        return nome_classificador(str(s)) if s else ""
    return f"{nome_classificador(m.group(1))} · {INFO_VARIANTES.get(m.group(2), {}).get('nome', m.group(2))}"


def _modelos(a):
    from . import registro
    if a.acao == "catalogo":
        import textwrap
        from .catalogo import INFO_CLASSIFICADORES, INFO_REGRESSORES
        from .experimentos import INFO_VARIANTES

        def bloco(cod, titulo, *textos):
            print(f"\n  {cod}\n    {titulo}")
            for t in textos:
                if t:
                    print(textwrap.fill(t, 100, initial_indent="      ", subsequent_indent="      "))
        print("Classificadores (nomes para --algoritmos):")
        for k, v in INFO_CLASSIFICADORES.items():
            bloco(k, f"{v['nome']} — {v['ajuste']} [{v['familia']}]", v["o_que"], v.get("parametros"))
        print("\nRepresentações da curva (nomes para --variantes):")
        for k, v in INFO_VARIANTES.items():
            bloco(k, v["nome"], v["o_que"])
        print("\nRegressores da carga (todos são comparados):")
        for k, v in INFO_REGRESSORES.items():
            bloco(k, f"{v['nome']} — {v['ajuste']}", v["o_que"])
        return
    if a.acao == "listar":
        lista = registro.listar(a.modelos)
        if not lista:
            print(f"Nenhum modelo em {a.modelos}/: rode fiep experimento.")
            return
        import pandas as pd
        df = pd.DataFrame(lista)[["em_uso", "id", "modelo", "protocolo", "teste_acuracia", "teste_balanced_accuracy",
                                  "teste_roc_auc", "teste_amostra_balanced_accuracy", "n_amostras"]]
        df["em_uso"] = df["em_uso"].map({True: "*", False: ""})
        df["modelo"] = df["modelo"].map(_nome_modelo)
        print(df.round(3).to_string(index=False))
        print("\n* = em uso. Detalhes: fiep modelos mostrar --id <id> · trocar: fiep modelos ativar --id <id>")
        return
    if not a.id:
        raise ValueError("informe --id (veja os ids com fiep modelos listar)")
    if a.acao == "ativar":
        registro.ativar(a.id, a.modelos)
        print(f"Modelo {a.id} em uso (plataforma e fiep prever).")
    elif a.acao == "mostrar":
        d = registro.detalhe(a.id, a.modelos, a.resultados)
        for k in ("id", "modelo", "protocolo", "n_amostras", "limiar", "teste_acuracia", "teste_balanced_accuracy",
                  "teste_sensibilidade", "teste_especificidade", "teste_roc_auc", "teste_amostra_balanced_accuracy",
                  "validacao_balanced_accuracy", "cv_balanced_accuracy", "regressor"):
            v = d.get(k)
            if k == "modelo":
                v = f"{_nome_modelo(v)}   ({v})"
            elif k == "regressor" and v:
                from .catalogo import nome_regressor
                v = f"{nome_regressor(v)}   ({v})"
            print(f"{k:32s} {round(v, 3) if isinstance(v, float) else v}")
        if d["comparacao"]:
            import pandas as pd
            cols = ["variante", "modelo", "val_balanced_accuracy", "teste_balanced_accuracy", "teste_roc_auc"]
            print("\nComparação (10 primeiras):")
            tab = pd.DataFrame(d["comparacao"])[cols].head(10).round(3)
            from .catalogo import nome_classificador
            from .experimentos import INFO_VARIANTES
            tab["modelo"] = tab["modelo"].map(nome_classificador)
            tab["variante"] = tab["variante"].map(lambda x: INFO_VARIANTES.get(x, {}).get("nome", x))
            print(tab.rename(columns={"modelo": "algoritmo", "variante": "representação"}).to_string(index=False))


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
    if a.acao == "zerar":
        if not a.sim:
            alvo = a.db or os.environ.get("FIEP_DB_URL") or "dados/fiep.db"
            print(f"Isto apaga TODAS as coletas, amostras, medições, QC e previsões de {alvo}"
                  + ("" if a.sem_usuarios else " (as contas de usuário ficam)") + ".")
            if input("Digite ZERAR para confirmar: ").strip() != "ZERAR":
                print("Nada foi apagado.")
                return
        r = db.zerar(a.db, manter_usuarios=not a.sem_usuarios, dados_exemplo=not a.sem_exemplo)
        print("Banco zerado e recriado" + (" com os dados de exemplo." if r["dados_exemplo"] else " vazio."))
        if r["backup"]:
            print(f"Cópia do banco anterior: {r['backup']}")
        print(f"Contas de usuário mantidas, com as mesmas senhas: {r['usuarios_mantidos']}"
              + (f" ({', '.join(r['emails'])})" if r["emails"] else " (crie o admin: fiep usuario criar --papel admin ...)"))
        print("Se a plataforma estava aberta, reinicie o fiep servir. Esqueceu a senha: fiep usuario senha --email <e-mail>")
        alvo = a.db or os.environ.get("FIEP_DB_URL") or "dados/fiep.db"
        print(f"Modelos em modelos/ não foram apagados. Para treinar de novo: fiep experimento --db {alvo}"
              + (" --com-exemplo" if r["dados_exemplo"] else "") + "  (ou Modelos → Treinar modelos)")
        return
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
            if db.id_empresa_exemplo(con) is not None:
                print(f"Sem dados em {base} além do exemplo, que já está no banco.")
                print(db.resumo(con).to_string(index=False))
                return
            print(f"Sem dados em {base}: carregando o case de demonstração.")
            r = db.carregar_exemplo(con)
            print(f"{r['amostras']} amostras, {r['medicoes']} medições.")
            return
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
            n_qc = db.gravar_qc(con, avaliar(ds.medicoes, ds.pontos, _cfg(a)))
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


DB_AJUDA = "arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou dados/fiep.db)"
CONFIG_AJUDA = "arquivo de configuração (padrão: variável FIEP_CONFIG ou configs/default.toml)"


class _Fmt(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=34, width=110)


def _pt(p: argparse.ArgumentParser) -> None:
    p._positionals.title, p._optionals.title = "argumentos", "opções"
    p.add_argument("-h", "--help", action="help", help="mostra esta ajuda")


def construir_parser() -> argparse.ArgumentParser:
    from . import __version__
    ap = argparse.ArgumentParser(
        prog="fiep", formatter_class=_Fmt, add_help=False,
        description="Pipeline e plataforma FIEP: voltamogramas (.nox/Excel do NOVA) -> banco -> modelos -> "
                    "previsão de contaminação.",
        epilog="Fluxo típico:\n"
               "  fiep planilha --entrada dados/empresa1      # confere o que foi deduzido; rótulos em amostras.csv\n"
               "  fiep db importar --entrada dados            # grava no banco (com QC e cópia em Excel)\n"
               "  fiep experimento --artigo                   # treina, compara e registra o melhor modelo\n"
               "  fiep servir                                 # plataforma web com login\n"
               "Ajuda de cada comando: fiep <comando> -h · Lista completa: docs/COMANDOS.md")
    _pt(ap)
    ap.add_argument("-v", "--verbose", action="store_true", help="mostra o andamento (logs INFO)")
    ap.add_argument("--version", action="version", version=f"fiep {__version__}", help="mostra a versão")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<comando>", title="comandos")

    def cmd(nome, ajuda, fn, descricao=None):
        p = sub.add_parser(nome, help=ajuda, description=descricao or ajuda, formatter_class=_Fmt, add_help=False)
        _pt(p)
        p.set_defaults(fn=fn)
        return p

    # ------------------------------------------------------------------ dados
    p = cmd("planilha", "gera amostras.csv (1 linha por amostra) e metadados_nox.csv já preenchidos", _planilha,
            "Lê os .nox/Excel de uma pasta e deduz amostra (pasta), eletrodo (E1.. no nome ou canal), etapa do "
            "sensor e data. Cria metadados_nox.csv (conferência, 1 linha por arquivo) e amostras.csv "
            "(rótulo e carga, 1 linha por amostra). Rodar de novo só acrescenta o que é novo.")
    p.add_argument("--entrada", required=True, help="pasta do lote (ex.: dados/empresa1)")
    p.add_argument("--config", help=CONFIG_AJUDA)

    p = cmd("excel", "converte .nox para Excel no formato do NOVA", _excel)
    p.add_argument("--entrada", required=True, help="pasta com .nox (ex.: dados/empresa1)")
    p.add_argument("--saida", help="pasta de saída (padrão: dados/excel/<lote>)")
    p.add_argument("--refazer", action="store_true", help="converte de novo mesmo se o Excel já existir")

    p = cmd("db", "banco de dados: migrar, importar, resumo, sql, exportar, exemplo, zerar", _db,
            "Ações:\n"
            "  migrar    cria/atualiza o banco pelas migrations (com os dados de exemplo, salvo --sem-exemplo)\n"
            "  importar  lê --entrada (.nox, Excel/CSV do NOVA, planilhas), roda o QC e grava; com a pasta dados/,\n"
            "            o que está em treino/ validacao/ teste/ é gravado com o seu conjunto\n"
            "  resumo    contagens (amostras, medições, réplicas completas, QC...)\n"
            "  sql       consulta livre, ex.: fiep db sql \"SELECT * FROM v_replicatas WHERE n_aprovadas < 3\"\n"
            "  exportar  tudo para Excel (uma aba por tabela) ou CSV\n"
            "  exemplo   carrega o case de demonstração (--remover para apagar)\n"
            "  zerar     apaga todos os dados e recria o banco (guarda uma cópia em dados/backup/; mantém as\n"
            "            contas de usuário, salvo --sem-usuarios; pede confirmação, salvo --sim)")
    p.add_argument("acao", choices=["migrar", "importar", "resumo", "exportar", "sql", "exemplo", "zerar"],
                   help="o que fazer")
    p.add_argument("consulta", nargs="?", help="consulta SQL (ação sql)")
    p.add_argument("--db", help=DB_AJUDA)
    p.add_argument("--entrada", help="importar: pasta com os dados (ex.: dados)")
    p.add_argument("--empresa", help="importar: nome da empresa dos dados")
    p.add_argument("--conjunto", choices=["treino", "validacao", "teste"],
                   help="importar: grava tudo como deste conjunto (padrão: sorteio, ou o da subpasta)")
    p.add_argument("--sem-excel", action="store_true", help="importar: não gerar a cópia em Excel (dados/excel/)")
    p.add_argument("--sem-exemplo", action="store_true", help="migrar/zerar: não carregar os dados de exemplo")
    p.add_argument("--sem-usuarios", action="store_true", help="zerar: apagar também as contas de usuário")
    p.add_argument("--sim", action="store_true", help="zerar: não pedir confirmação (scripts)")
    p.add_argument("--remover", action="store_true", help="exemplo: apagar os dados de exemplo")
    p.add_argument("--formato", choices=["xlsx", "csv"], default="xlsx", help="exportar: formato (padrão xlsx)")
    p.add_argument("--saida", help="exportar/sql: arquivo ou pasta de saída")
    p.add_argument("--config", help=CONFIG_AJUDA)

    # ------------------------------------------------------------------ modelos
    p = cmd("experimento", "divide 50/25/25, compara representações x modelos e registra o melhor", _experimento,
            "Divide as amostras em treino/validação/teste (padrão 50/25/25, por amostra, estratificado), ajusta "
            "5 representações x 15 algoritmos no treino (lista: fiep modelos catalogo), escolhe pela validação, re-treina com treino+validação e "
            "mede uma vez no teste. Registra o melhor em modelos/ (usado pela plataforma) e gera figuras/tabelas.")
    p.add_argument("--dados", default="dados",
                   help="pasta de dados (padrão: dados). Solto em dados/ = sorteio; dados/treino, dados/validacao e "
                        "dados/teste = somados ao conjunto")
    p.add_argument("--db", help="usar o banco em vez das pastas (" + DB_AJUDA + ")")
    p.add_argument("--filtro", help="com --db: filtro SQL das medições, ex.: \"empresa_id = 2\"")
    p.add_argument("--filtro-treino", help="com --db: filtro SQL de amostras que vão inteiras para o treino")
    p.add_argument("--filtro-validacao", help="com --db: idem, para a validação")
    p.add_argument("--filtro-teste", help="com --db: idem, para o teste (ex.: outra empresa)")
    p.add_argument("--com-exemplo", action="store_true",
                   help="com --db: inclui os dados de exemplo mesmo havendo dados reais")
    p.add_argument("--saida", default="resultados", help="pasta dos resultados (padrão: resultados)")
    p.add_argument("--modelos", default="modelos", help="pasta onde o modelo é registrado (padrão: modelos)")
    p.add_argument("--rapido", action="store_true", help="menos variantes e modelos (para testar)")
    p.add_argument("--algoritmos", help="só estes classificadores, separados por vírgula (lista: fiep modelos catalogo)")
    p.add_argument("--variantes", help="só estas representações, separadas por vírgula (lista: fiep modelos catalogo)")
    p.add_argument("--nao-ativar", action="store_true",
                   help="registra o modelo sem trocar o que está em uso (para comparar)")
    p.add_argument("--artigo", action="store_true", help="copia figuras, tabelas e números para o artigo")
    p.add_argument("--artigo-pasta", default="artigo/gerado", help="destino do --artigo (padrão: artigo/gerado)")
    p.add_argument("--config", help=CONFIG_AJUDA)

    p = cmd("prever", "classifica dados novos com o modelo registrado (por amostra e por eletrodo)", _prever)
    p.add_argument("--entrada", required=True, help="pasta com .nox/Excel (uma subpasta por amostra)")
    p.add_argument("--modelo", default="modelos", help="pasta de modelos (usa ATUAL) ou a pasta de um modelo")
    p.add_argument("--saida", help="CSV com o resultado por eletrodo (+ <nome>_amostras.csv)")
    p.add_argument("--db", help="gravar as previsões neste banco")
    p.add_argument("--config", help=CONFIG_AJUDA + "; usa os [niveis] de contaminação dela")

    # ------------------------------------------------------------------ plataforma
    p = cmd("modelos", "modelos treinados: listar, mostrar, ativar, catalogo", _modelos,
            "Ações:\n"
            "  listar    modelos registrados, com as métricas no teste (* = em uso)\n"
            "  mostrar   métricas e comparação de um modelo (--id)\n"
            "  ativar    passa a usar o modelo --id na plataforma e no fiep prever\n"
            "  catalogo  algoritmos e representações disponíveis para o fiep experimento")
    p.add_argument("acao", choices=["listar", "mostrar", "ativar", "catalogo"], help="o que fazer")
    p.add_argument("--id", help="id do modelo (ex.: 20261022-102514)")
    p.add_argument("--modelos", default="modelos", help="pasta de modelos (padrão: modelos)")
    p.add_argument("--resultados", default="resultados", help="pasta dos experimentos (padrão: resultados)")

    p = cmd("servir", "abre a plataforma web (login, coletas, amostras, previsão)", _servir,
            "Serve o frontend compilado (web/dist) e a API. Primeiro acesso: fiep usuario criar --papel admin. "
            "Variáveis de ambiente: ver docs/PLATAFORMA.md.")
    p.add_argument("--db", help=DB_AJUDA)
    p.add_argument("--modelos", default="modelos", help="pasta de modelos (padrão: modelos)")
    p.add_argument("--host", default="127.0.0.1", help="endereço (0.0.0.0 para a rede local)")
    p.add_argument("--porta", type=int, default=8000, help="porta (padrão: 8000)")
    p.add_argument("--sem-compilar", action="store_true",
                   help="não compilar a tela automaticamente quando ela estiver desatualizada")

    p = cmd("usuario", "contas da plataforma: criar, listar, senha, desativar", _usuario,
            "criar e senha pedem a senha no terminal (ou leem FIEP_SENHA_NOVA). Perfis: admin (tudo), "
            "colaborador (envia e edita dados), leitor (consulta).")
    p.add_argument("acao", choices=["criar", "listar", "senha", "desativar"], help="o que fazer")
    p.add_argument("--email", help="e-mail (login) da conta")
    p.add_argument("--nome", help="nome completo (criar)")
    p.add_argument("--papel", choices=["admin", "colaborador", "leitor"], default="colaborador",
                   help="perfil (criar; padrão: colaborador)")
    p.add_argument("--instituicao", help="instituição (criar)")
    p.add_argument("--db", help=DB_AJUDA)

    # ------------------------------------------------------------------ manutenção
    p = cmd("verificar", "diagnóstico da instalação (dependências, banco, modelo, frontend)", _verificar)
    p.add_argument("--db", help=DB_AJUDA)
    p.add_argument("--modelos", default="modelos", help="pasta de modelos (padrão: modelos)")

    p = cmd("docs", "regera docs/COMANDOS.md a partir desta ajuda", _docs)
    p.add_argument("--saida", default="docs/COMANDOS.md", help="arquivo (padrão: docs/COMANDOS.md)")

    # ------------------------------------------------------------------ fluxo antigo, só arquivos
    p = cmd("ingerir", "(avançado) lê .nox/tabelas e grava CSVs canônicos, sem banco", _ingerir)
    p.add_argument("--entrada", required=True, help="pasta com os dados")
    p.add_argument("--saida", default="dados/processados", help="pasta de saída (padrão: dados/processados)")
    p.add_argument("--config", help=CONFIG_AJUDA)

    p = cmd("qc", "(avançado) controle de qualidade dos CSVs canônicos", _qc)
    p.add_argument("--dados", default="dados/processados", help="pasta do ingerir (padrão: dados/processados)")
    p.add_argument("--config", help=CONFIG_AJUDA)

    p = cmd("treinar", "(avançado) treino rápido com a configuração, sem comparar variantes", _treinar)
    p.add_argument("--dados", default="dados/processados", help="pasta do ingerir (padrão: dados/processados)")
    p.add_argument("--db", help="treinar com o banco (" + DB_AJUDA + ")")
    p.add_argument("--filtro", help="com --db: filtro SQL das medições")
    p.add_argument("--modelos", default="modelos", help="pasta de modelos (padrão: modelos)")
    p.add_argument("--config", help=CONFIG_AJUDA)

    p = cmd("tudo", "(avançado) ingerir + treinar", _tudo)
    p.add_argument("--entrada", required=True, help="pasta com os dados")
    p.add_argument("--dados", default="dados/processados", help="pasta intermediária (padrão: dados/processados)")
    p.add_argument("--db", help="também importar para este banco e treinar a partir dele")
    p.add_argument("--filtro", help="com --db: filtro SQL das medições")
    p.add_argument("--modelos", default="modelos", help="pasta de modelos (padrão: modelos)")
    p.add_argument("--config", help=CONFIG_AJUDA)
    return ap


def comandos_markdown() -> str:
    """Referência de todos os comandos e opções (docs/COMANDOS.md), gerada da própria ajuda."""
    ap = construir_parser()
    sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
    partes = ["# Comandos `fiep`", "",
              "Gerado por `fiep docs` a partir da ajuda dos comandos — não edite à mão. "
              "Sem instalar o pacote, use `python -m fiep` na raiz do repositório.", "",
              "| Comando | Para quê |", "|---|---|"]
    ajudas = {a.dest: a.help for a in sub._choices_actions}
    partes += [f"| [`fiep {n}`](#fiep-{n}) | {ajudas.get(n, '')} |" for n in sub.choices]
    for n, p in sub.choices.items():
        partes += ["", f"## fiep {n}", "", "```", p.format_help().replace("usage:", "uso:").rstrip(), "```"]
    return "\n".join(partes) + "\n"


def _docs(a):
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.saida).write_text(comandos_markdown(), encoding="utf-8")
    print(f"{a.saida} atualizado.")


def _verificar(a):
    import importlib
    import platform
    ok = True

    def linha(estado, item, detalhe=""):
        nonlocal ok
        ok &= estado != "ERRO"
        print(f"[{estado:^5}] {item}" + (f" — {detalhe}" if detalhe else ""))

    from . import __version__
    linha("ok", f"Python {platform.python_version()} ({sys.executable})")
    linha("ok", f"pacote fiep {__version__} em {Path(__file__).resolve().parent}")
    for mod, extra in [("pandas", ""), ("sklearn", ""), ("sqlalchemy", ""), ("alembic", ""), ("bcrypt", ""),
                       ("openpyxl", ""), ("matplotlib", ""), ("fastapi", "[api]"), ("uvicorn", "[api]"),
                       ("jwt", "[api]"), ("multipart", "[api]")]:
        try:
            importlib.import_module(mod)
            linha("ok", mod)
        except ImportError:
            linha("ERRO", mod, f'faltando: pip install -e ".{extra or ""}"'.replace('.""', '.'))
    cfg_arq = _arquivo_config(None)
    linha("ok" if cfg_arq else "aviso", "configuração", cfg_arq or "usando os valores de fábrica")
    try:
        from . import db
        from .orm import url_banco
        url = url_banco(a.db)
        if url.startswith("sqlite:///") and not Path(url[len("sqlite:///"):]).exists():
            linha("aviso", "banco", f"ainda não criado ({url}); é criado no primeiro uso, com os dados de exemplo")
            raise LookupError
        s = db.conectar(a.db)
        r = db.resumo(s).set_index("item")["total"]
        from .orm import url_banco
        linha("ok", "banco", f"{url_banco(a.db)} — {r['amostras']} amostras, {r['medições']} medições, "
                             f"{int(db.sql(s, 'SELECT COUNT(*) FROM usuarios').iloc[0, 0])} usuário(s)")
        if not int(db.sql(s, "SELECT COUNT(*) FROM usuarios WHERE papel = 'admin' AND ativo").iloc[0, 0]):
            linha("aviso", "nenhum admin", "fiep usuario criar --email voce@... --papel admin")
        s.close()
    except LookupError:
        pass
    except Exception as e:  # noqa: BLE001
        linha("ERRO", "banco", str(e).splitlines()[0])
    try:
        from .model import carregar
        c = carregar(a.modelos)["cartao"]
        linha("ok", "modelo", f"{c['id']} — {c.get('modelo')}")
    except Exception:  # noqa: BLE001
        linha("aviso", "modelo", f"nenhum em {a.modelos}/: rode fiep experimento")
    raiz = Path(__file__).resolve().parents[1]
    web = raiz / "web" / "dist" / "index.html"
    est = estado_frontend(raiz)
    linha("ok" if est == "ok" else "aviso", "frontend",
          str(web.parent) if est == "ok" else
          ("não compilado" if est == "ausente" else "DESATUALIZADO (a tela mostra a versão antiga)")
          + ": cd web; npm install; npm run build — ou só fiep servir, que compila sozinho")
    print("\nTudo certo." if ok else "\nCorrija os itens com ERRO.")
    if not ok:
        raise SystemExit(1)


def _arquivo_config(caminho: str | None) -> str | None:
    """--config, ou FIEP_CONFIG, ou configs/default.toml (se existir)."""
    for c in (caminho, os.environ.get("FIEP_CONFIG"), "configs/default.toml"):
        if c and Path(c).exists():
            return c
    if caminho:
        raise FileNotFoundError(f"configuração não encontrada: {caminho}")
    return None


def _cfg(a) -> dict:
    return load_config(_arquivo_config(getattr(a, "config", None)))


def main(argv=None):
    for fluxo in (sys.stdout, sys.stderr):              # console do Windows: acentos e símbolos sem quebrar
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = construir_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        a.fn(a)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
