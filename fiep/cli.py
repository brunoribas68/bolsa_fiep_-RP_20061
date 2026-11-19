"""Linha de comando do projeto FIEP (`fiep <comando>` ou `python -m fiep <comando>`).

Ajuda: `fiep -h` e `fiep <comando> -h`. Todas as opções: docs/COMANDOS.md (gerado por `fiep docs`).
O README e docs/COMANDOS.md são conferidos pelos testes (tests/test_docs.py): um comando novo precisa
aparecer no README.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

DB_AJUDA = "arquivo SQLite ou URL do banco (padrão: variável FIEP_DB_URL ou dados/fiep.db)"
MODELOS_AJUDA = "pasta dos modelos (padrão: modelos)"


# ----------------------------------------------------------------------------- dados e modelo
def _rna(a):
    import json
    from . import db, genossensor as g, modelagem as m
    if a.acao == "pastas":
        if not a.entrada:
            raise ValueError("informe --entrada (onde criar contaminado/ e nao_contaminado/)")
        for p in g.criar_pastas(a.entrada):
            print("pronta:", p)
        print("contaminado/: só dpv-RNA-<conc>-Ej  |  nao_contaminado/: só dpv-branco-Ej")
        return
    if a.acao == "prever":
        if not a.entrada:
            raise ValueError("informe --entrada (um .nox ou uma pasta com .nox)")
        alvo = Path(a.entrada)
        arquivos = sorted(alvo.rglob("*.nox")) if alvo.is_dir() else [alvo]
        if not arquivos:
            raise FileNotFoundError(f"nenhum .nox em {alvo}")
        pacote = m.carregar(a.modelos, a.id)
        c = pacote["cartao"]
        print(f"Modelo {c['id']}: {c['algoritmo_nome']} · {c['representacao_nome']} "
              f"(acurácia balanceada {c['ab_referencia']:.3f}, {c['referencia']})\n")
        res = m.prever_arquivos(pacote, arquivos)
        for r in res:
            p = r.get("prob_contaminado")
            info = f"  [nome diz: {r['tipo_informado']}]" if r.get("tipo_informado") else ""
            print(f"{r['arquivo']:40s} {r['resultado']:16s} " + (f"p = {p:.2f}" if p is not None else "")
                  + info + (f"\n    {r['motivo']}" if r.get("motivo") else ""))
        if a.salvar:
            n = m.gravar_predicoes(db.conectar(a.db), res, c)
            print(f"\n{n} previsão(ões) gravada(s) no banco.")
        return
    con = db.conectar(a.db)
    if a.acao == "importar":
        if not a.entrada:
            raise ValueError("informe --entrada (pasta com os .nox)")
        r = g.importar(con, a.entrada, empresa=a.empresa, elemento=a.elemento, eletrodo=a.eletrodo,
                       bacteria=a.bacteria)
        print(f"{r['lidos']} arquivo(s) lido(s): {r['gravados']} gravado(s), {r['ja_no_banco']} já estavam no banco, "
              f"{r['nao_gravados']} não gravado(s). {r['ligados_ao_branco']} RNA ligado(s) ao branco do eletrodo.")
        for x in r["avisos"]:
            print("  aviso:", x)
        print()
        a.acao, a.saida = "tabela", None
    df = g.tabela(con)
    if df.empty:
        print("A base está vazia. Comece com: fiep rna importar --entrada <pasta com .nox>")
        return
    if a.acao == "tabela":
        cols = ["id", "arquivo", "eletrodo_id", "tipo", "concentracao", "e_pico_v", "i_pico_ua", "altura_ua",
                "queda_pct", "abaixo_do_branco", "qc_flag"]
        print(df[cols].round(3).to_string(index=False))
        n = df["tipo"].value_counts()
        print(f"\n{n.get('branco', 0)} branco(s), {n.get('rna', 0)} RNA, {df['eletrodo_id'].nunique()} eletrodo(s)")
        contra = df[df["abaixo_do_branco"] == False]  # noqa: E712
        if len(contra):
            print(f"ATENÇÃO: {len(contra)} RNA com pico acima do branco do eletrodo: {', '.join(contra['arquivo'])}")
        cal = g.calibracao(df)
        if cal:
            print(f"Calibração (queda % x log10 conc.): inclinação {cal['inclinacao_pct_por_decada']} %/década, "
                  f"R² {cal['r2']}, LOD {cal['lod_ng_ml'] if cal['lod_ng_ml'] is not None else '— (' + cal['lod_motivo'] + ')'}")
        if a.saida:
            completa = g.tabela(con, incluir_curvas=a.saida.endswith(".csv"))
            completa.to_csv(a.saida, index=False) if a.saida.endswith(".csv") else completa.to_excel(a.saida, index=False)
            print(f"\nBase salva em {a.saida}")
        return
    # treinar
    def andamento(etapa, frac):
        if a.verbose:
            print(f"  {frac:5.0%}  {etapa}")
    pacote = m.treinar(g.tabela(con, incluir_curvas=True), algoritmos=a.algoritmos, variantes=a.representacoes,
                       seed=a.seed, rapido=a.rapido, progresso=andamento)
    destino = m.salvar(pacote, a.modelos, ativar=not a.sem_ativar, s=con)
    c = pacote["cartao"]
    print(_resumo_cartao(c))
    print(f"\nModelo salvo em {destino}" + ("" if a.sem_ativar else " e em uso (plataforma e fiep rna prever)."))
    if a.saida:
        Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
        Path(a.saida).write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def _resumo_cartao(c: dict, n_placar: int = 10) -> str:
    import pandas as pd
    from .modelagem import INFO_VARIANTES
    from .catalogo import nome_classificador
    d = c["dados"]
    linhas = [f"Modelo {c['id']}: {c['algoritmo_nome']} · {c['representacao_nome']}",
              f"Dados: {d['n_ensaios']} curvas ({d['n_branco']} branco, {d['n_rna']} RNA) de {d['n_eletrodos']} eletrodo(s)",
              f"Validação: {c['validacao']}"]
    mc = c["metricas_cv"]
    linhas.append(f"Validação cruzada: acurácia balanceada {mc['balanced_accuracy']:.3f}"
                  + (f", AUC {mc['roc_auc']:.3f}" if mc.get("roc_auc") is not None else ""))
    if c["metricas_teste"]:
        mt = c["metricas_teste"]
        linhas.append(f"Teste ({mt['n']} curvas, eletrodos {', '.join(d['eletrodos_teste'])}): acurácia balanceada "
                      f"{mt['balanced_accuracy']:.3f}, sensibilidade {mt['sensibilidade']:.3f}, especificidade "
                      f"{mt['especificidade']:.3f}")
    linhas += [f"AVISO: {x}" for x in c["avisos"]]
    if not c["confiavel"]:
        linhas.append("AVISO: acurácia balanceada abaixo de 0,7: as previsões saem INCONCLUSIVO.")
    p = pd.DataFrame(c["placar"]).head(n_placar)
    p["representação"] = p["representacao"].map(lambda v: INFO_VARIANTES.get(v, {}).get("nome", v))
    p["algoritmo"] = p["algoritmo"].map(nome_classificador)
    linhas += ["", "Melhores combinações (validação cruzada):",
               p[["posicao", "representação", "algoritmo", "balanced_accuracy", "roc_auc"]]
               .round(3).to_string(index=False)]
    return "\n".join(linhas)


def _modelos(a):
    from . import modelagem as m
    if a.acao == "catalogo":
        from .catalogo import INFO_CLASSIFICADORES
        print("Representações da curva:")
        for k, v in m.INFO_VARIANTES.items():
            print(f"  {k:10s} {v['nome']}: {v['o_que']}")
        print("\nAlgoritmos:")
        for k, v in INFO_CLASSIFICADORES.items():
            print(f"  {k:15s} {v['nome']} — {v['ajuste']}")
        return
    if a.acao == "listar":
        ms = m.listar(a.modelos)
        if not ms:
            print(f"Nenhum modelo em {a.modelos}/: treine com fiep rna treinar")
        for c in ms:
            print(f"{'*' if c['em_uso'] else ' '} {c['id']}  {c['algoritmo_nome']} · {c['representacao_nome']}  "
                  f"AB {c['ab_referencia']:.3f} ({c['referencia']})  {c['dados']['n_ensaios']} curvas")
        return
    if not a.id:
        raise ValueError("informe --id (veja os ids em fiep modelos listar)")
    if a.acao == "mostrar":
        print(_resumo_cartao(m.cartao(a.id, a.modelos), n_placar=60))
    else:
        m.ativar_modelo(a.id, a.modelos)
        print(f"Modelo {a.id} em uso.")


def _excel(a):
    from .excel import converter_pasta
    gerados = converter_pasta(a.entrada, a.saida, refazer=a.refazer)
    print(f"{len(gerados)} arquivo(s) convertido(s)" + (f" em {gerados[0].parent}" if gerados else " (já estavam em dia)"))


def _db(a):
    from . import db
    alvo = a.db or os.environ.get("FIEP_DB_URL") or "dados/fiep.db"
    if a.acao == "zerar":
        if not a.sim:
            print(f"Isto apaga TODAS as coletas, ensaios, modelos registrados e previsões de {alvo}"
                  + ("" if a.sem_usuarios else " (as contas de usuário ficam)") + ".")
            if input("Digite ZERAR para confirmar: ").strip() != "ZERAR":
                print("Nada foi apagado.")
                return
        r = db.zerar(a.db, manter_usuarios=not a.sem_usuarios)
        print("Banco zerado e recriado vazio.")
        if r["backup"]:
            print(f"Cópia do banco anterior: {r['backup']}")
        print(f"Contas de usuário mantidas, com as mesmas senhas: {r['usuarios_mantidos']}"
              + (f" ({', '.join(r['emails'])})" if r["emails"] else " (crie o admin: fiep usuario criar --papel admin ...)"))
        print("Próximos passos: fiep rna importar --entrada dados/rna  e  fiep rna treinar. "
              "Se a plataforma estava aberta, reinicie o fiep servir.")
        return
    con = db.conectar(a.db)
    if a.acao == "migrar":
        print(f"Banco {alvo} atualizado.")
    elif a.acao == "sql":
        if not a.consulta:
            raise ValueError('informe a consulta, ex.: fiep db sql "SELECT tipo, COUNT(*) FROM ensaios GROUP BY tipo"')
        df = db.sql(con, a.consulta)
        print(df.to_string(index=False, max_rows=60))
        if a.saida:
            df.to_csv(a.saida, index=False)
            print(f"\n{len(df)} linhas salvas em {a.saida}")


# ----------------------------------------------------------------------------- plataforma
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


def _usuario(a):
    import getpass

    from . import db, usuarios
    from .orm import Usuario
    s = db.conectar(a.db)
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
    for mod, extra in [("pandas", ""), ("sklearn", ""), ("scipy", ""), ("sqlalchemy", ""), ("alembic", ""),
                       ("bcrypt", ""), ("openpyxl", ""), ("joblib", ""), ("fastapi", "[api]"), ("uvicorn", "[api]"),
                       ("jwt", "[api]"), ("multipart", "[api]")]:
        try:
            importlib.import_module(mod)
            linha("ok", mod)
        except ImportError:
            linha("ERRO", mod, f'faltando: pip install -e ".{extra or ""}"'.replace('.""', '.'))
    try:
        from . import db
        from .orm import url_banco
        url = url_banco(a.db)
        if url.startswith("sqlite:///") and not Path(url[len("sqlite:///"):]).exists():
            linha("aviso", "banco", f"ainda não criado ({url}); é criado no primeiro uso")
            raise LookupError
        s = db.conectar(a.db)
        n = db.sql(s, "SELECT tipo, COUNT(*) AS n FROM ensaios GROUP BY tipo").set_index("tipo")["n"].to_dict()
        linha("ok", "banco", f"{url} — {n.get('branco', 0)} branco(s), {n.get('rna', 0)} RNA, "
                             f"{int(db.sql(s, 'SELECT COUNT(*) FROM usuarios').iloc[0, 0])} usuário(s)")
        if not int(db.sql(s, "SELECT COUNT(*) FROM usuarios WHERE papel = 'admin' AND ativo").iloc[0, 0]):
            linha("aviso", "nenhum admin", "fiep usuario criar --email voce@... --papel admin")
        s.close()
    except LookupError:
        pass
    except Exception as e:  # noqa: BLE001
        linha("ERRO", "banco", str(e).splitlines()[0])
    try:
        from .modelagem import carregar
        c = carregar(a.modelos)["cartao"]
        linha("ok", "modelo", f"{c['id']} — {c['algoritmo_nome']} · {c['representacao_nome']}")
    except Exception:  # noqa: BLE001
        linha("aviso", "modelo", f"nenhum em {a.modelos}/: rode fiep rna treinar")
    raiz = Path(__file__).resolve().parents[1]
    est = estado_frontend(raiz)
    linha("ok" if est == "ok" else "aviso", "frontend",
          str(raiz / "web" / "dist") if est == "ok" else
          ("não compilado" if est == "ausente" else "DESATUALIZADO (a tela mostra a versão antiga)")
          + ": cd web; npm install; npm run build — ou só fiep servir, que compila sozinho")
    print("\nTudo certo." if ok else "\nCorrija os itens com ERRO.")
    if not ok:
        raise SystemExit(1)


# ----------------------------------------------------------------------------- parser
class _Fmt(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=34, width=110)


def _pt(p: argparse.ArgumentParser) -> None:
    p._positionals.title, p._optionals.title = "argumentos", "opções"
    p.add_argument("-h", "--help", action="help", help="mostra esta ajuda")


def construir_parser() -> argparse.ArgumentParser:
    from . import __version__
    from .catalogo import INFO_CLASSIFICADORES
    from .modelagem import VARIANTES
    ap = argparse.ArgumentParser(
        prog="fiep", formatter_class=_Fmt, add_help=False,
        description="Genossensor FIEP: voltamogramas DPV (.nox) de branco e de RNA -> banco -> modelo pela curva "
                    "-> previsão de contaminação.",
        epilog="Fluxo típico:\n"
               "  fiep rna pastas --entrada dados/rna       # contaminado/ (RNA) e nao_contaminado/ (branco)\n"
               "  fiep rna importar --entrada dados/rna     # grava no banco, com o pico de cada curva\n"
               "  fiep rna treinar                          # compara os modelos e registra o melhor\n"
               "  fiep rna prever --entrada nova.nox        # classifica uma medição nova\n"
               "  fiep servir                               # plataforma web com login\n"
               "Ajuda de cada comando: fiep <comando> -h · Lista completa: docs/COMANDOS.md")
    _pt(ap)
    ap.add_argument("-v", "--verbose", action="store_true", help="mostra o andamento")
    ap.add_argument("--version", action="version", version=f"fiep {__version__}", help="mostra a versão")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="<comando>", title="comandos")

    def cmd(nome, ajuda, fn, descricao=None):
        p = sub.add_parser(nome, help=ajuda, description=descricao or ajuda, formatter_class=_Fmt, add_help=False)
        _pt(p)
        p.set_defaults(fn=fn)
        return p

    p = cmd("rna", "genossensor: pastas, importar, tabela, treinar, prever", _rna,
            "Ações:\n"
            "  pastas    cria contaminado/ (só RNA) e nao_contaminado/ (só branco) em --entrada\n"
            "  importar  lê os .nox DPV de --entrada: do nome do arquivo (dpv-branco-E1, dpv-RNA-0,1-E1) tira o tipo,\n"
            "            a concentração (ng/mL) e o eletrodo; do procedimento do NOVA, o elemento de captura. Mede o\n"
            "            pico e liga cada RNA ao branco do mesmo eletrodo. Arquivo na pasta errada, de outra etapa\n"
            "            (bare, tratado...) ou sem eletrodo não é gravado. Correções: ensaios.csv na pasta\n"
            "  tabela    mostra a base (pico, queda em relação ao branco, calibração); --saida base.xlsx/.csv salva\n"
            "  treinar   compara 4 representações da curva x 15 algoritmos (validação por eletrodo), mede o melhor\n"
            "            no teste (se houver eletrodos suficientes) e o registra como modelo em uso\n"
            "  prever    classifica os .nox de --entrada (arquivo ou pasta) com o modelo em uso\n"
            "Dicionário de dados: docs/DICIONARIO_DADOS.md")
    p.add_argument("acao", choices=["pastas", "importar", "tabela", "treinar", "prever"], help="o que fazer")
    p.add_argument("--entrada", help="pastas/importar: pasta dos .nox; prever: um .nox ou uma pasta")
    p.add_argument("--db", help=DB_AJUDA)
    p.add_argument("--empresa", help="importar: empresa/laboratório dos dados")
    p.add_argument("--elemento", help="importar: elemento de captura de quem não tiver no procedimento")
    p.add_argument("--eletrodo", help="importar: ID do eletrodo de quem não tiver E1, E2.. no nome")
    p.add_argument("--bacteria", help="importar: bactéria de origem do RNA (ex.: E. coli)")
    p.add_argument("--algoritmos", nargs="+", choices=list(INFO_CLASSIFICADORES), metavar="ALG",
                   help="treinar: só estes algoritmos (padrão: os 15; lista em fiep modelos catalogo)")
    p.add_argument("--representacoes", nargs="+", choices=list(VARIANTES),
                   help="treinar: só estas representações da curva (padrão: todas)")
    p.add_argument("--seed", type=int, default=42, help="treinar: semente dos sorteios (padrão: 42)")
    p.add_argument("--rapido", action="store_true", help="treinar: só 3 algoritmos (teste rápido)")
    p.add_argument("--sem-ativar", action="store_true", help="treinar: registra sem trocar o modelo em uso")
    p.add_argument("--modelos", default="modelos", help=MODELOS_AJUDA)
    p.add_argument("--id", help="prever: usar este modelo em vez do que está em uso")
    p.add_argument("--salvar", action="store_true", help="prever: grava as previsões no banco")
    p.add_argument("--saida", help="tabela: .xlsx/.csv da base; treinar: .json com o cartão do modelo")

    p = cmd("modelos", "modelos treinados: listar, mostrar, ativar, catalogo", _modelos,
            "Ações:\n"
            "  listar    modelos registrados, com a acurácia balanceada de referência (* = em uso)\n"
            "  mostrar   dados, validação e a comparação completa de um modelo (--id)\n"
            "  ativar    passa a usar o modelo --id na plataforma e no fiep rna prever\n"
            "  catalogo  representações da curva e algoritmos comparados no treino")
    p.add_argument("acao", choices=["listar", "mostrar", "ativar", "catalogo"], help="o que fazer")
    p.add_argument("--id", help="id do modelo (ex.: 20261119-153012)")
    p.add_argument("--modelos", default="modelos", help=MODELOS_AJUDA)

    p = cmd("excel", "converte .nox para Excel no formato do NOVA", _excel)
    p.add_argument("--entrada", required=True, help="pasta com .nox")
    p.add_argument("--saida", help="pasta de saída (padrão: dados/excel/<lote>)")
    p.add_argument("--refazer", action="store_true", help="converte de novo mesmo se o Excel já existir")

    p = cmd("db", "banco de dados: migrar, sql, zerar", _db,
            "Ações:\n"
            "  migrar  cria/atualiza o banco\n"
            "  sql     consulta livre, ex.: fiep db sql \"SELECT tipo, COUNT(*) FROM ensaios GROUP BY tipo\"\n"
            "  zerar   apaga todos os dados e recria o banco (guarda uma cópia em dados/backup/; mantém as contas de\n"
            "          usuário, salvo --sem-usuarios; pede confirmação, salvo --sim). Também é o caminho para sair\n"
            "          de um banco da versão anterior (com o case de exemplo)")
    p.add_argument("acao", choices=["migrar", "sql", "zerar"], help="o que fazer")
    p.add_argument("consulta", nargs="?", help="consulta SQL (ação sql)")
    p.add_argument("--db", help=DB_AJUDA)
    p.add_argument("--saida", help="sql: salva o resultado em .csv")
    p.add_argument("--sem-usuarios", action="store_true", help="zerar: apagar também as contas de usuário")
    p.add_argument("--sim", action="store_true", help="zerar: não pedir confirmação (scripts)")

    p = cmd("servir", "abre a plataforma web (login, coletas, gráficos, modelos, previsão)", _servir,
            "Serve o frontend compilado (web/dist) e a API. Primeiro acesso: fiep usuario criar --papel admin. "
            "Variáveis de ambiente: ver docs/PLATAFORMA.md.")
    p.add_argument("--db", help=DB_AJUDA)
    p.add_argument("--modelos", default="modelos", help=MODELOS_AJUDA)
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

    p = cmd("verificar", "diagnóstico da instalação (dependências, banco, modelo, frontend)", _verificar)
    p.add_argument("--db", help=DB_AJUDA)
    p.add_argument("--modelos", default="modelos", help=MODELOS_AJUDA)

    p = cmd("docs", "regera docs/COMANDOS.md a partir desta ajuda", _docs)
    p.add_argument("--saida", default="docs/COMANDOS.md", help="arquivo (padrão: docs/COMANDOS.md)")
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
