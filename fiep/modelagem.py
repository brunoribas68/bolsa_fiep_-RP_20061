"""Modelo pela curva: cada voltamograma DPV sozinho é classificado em branco (não contaminado) ou RNA
(contaminado).

Treino (`fiep rna treinar`, ou o botão da tela Modelos):
1. Dados: os ensaios do banco aprovados (qc_flag diferente de FAIL). Rótulo: RNA = 1, branco = 0.
   Grupo: o eletrodo. Medições do mesmo eletrodo nunca ficam metade no treino e metade na avaliação,
   senão o modelo é avaliado num eletrodo que já viu.
2. Teste: com eletrodos suficientes, cerca de 25 % deles ficam guardados até o fim. Com poucos, não há
   teste independente e o resultado diz isso.
3. Validação cruzada por eletrodo no restante: cada representação da curva × cada um dos 15 algoritmos.
   Vence a maior acurácia balanceada (empate: o mais simples, na ordem do catálogo).
4. O vencedor é retreinado no restante e medido uma vez no teste.
5. Registro em `modelos/<id>/` e no banco; vira o modelo em uso, salvo `ativar=False`.

Previsão: lê o .nox, confere se a faixa de potencial cobre a do modelo, aplica a mesma representação e
devolve CONTAMINADO / NÃO CONTAMINADO com a probabilidade. Se a acurácia balanceada de referência do
modelo for menor que 0,7, o resultado sai INCONCLUSIVO.
"""
from __future__ import annotations

import datetime as dt
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .catalogo import classificadores, nome_classificador
from .pico import CAMPOS as CAMPOS_PICO
from .pico import linha_base, medir_pico

N_PONTOS = 100                 # pontos da curva na grade comum de potencial
MIN_POR_CLASSE = 3             # medições de branco e de RNA para treinar
MIN_ELETRODOS_TESTE = 8        # eletrodos para separar um teste independente
BA_CONFIAVEL = 0.7             # abaixo disso a previsão sai INCONCLUSIVO
TOLERANCIA_V = 0.02            # quanto a faixa de uma curva nova pode ficar aquém da do modelo
PASTA_MODELOS = "modelos"

INFO_VARIANTES = {
    "curva": dict(nome="Curva inteira",
                  o_que=f"A corrente em {N_PONTOS} potenciais igualmente espaçados na faixa comum das curvas. "
                        "O modelo vê tudo: altura, posição e forma do pico e a linha de base."),
    "forma": dict(nome="Forma da curva",
                  o_que="A curva inteira reescalada entre 0 e 1 (mínimo 0, máximo 1). Tira a diferença de "
                        "tamanho entre eletrodos e deixa só a forma; perde a altura absoluta do pico."),
    "derivada": dict(nome="Derivada da curva",
                     o_que="A inclinação da curva (filtro de Savitzky-Golay). Ignora deslocamentos da linha de "
                           "base e realça o formato do pico."),
    "base_vales": dict(nome="Curva sem a base (vale a vale)",
                       o_que="A curva inteira menos uma reta entre o ponto mais baixo de cada lado do pico: a base "
                             "fica plana em zero, como na correção linear do NOVA. Tira inclinação e deslocamento da "
                             "base, que variam de eletrodo para eletrodo."),
    "base_als": dict(nome="Curva sem a base (ALS)",
                     o_que="A curva inteira menos uma base suave que passa por baixo do sinal (mínimos quadrados "
                           "assimétricos, Eilers e Boelens 2005). Acompanha bases curvas, como a subida da dupla "
                           "camada nas pontas."),
    "pico": dict(nome="Medidas do pico",
                 o_que="Seis números: potencial e corrente do pico, corrente da base, altura acima da base, "
                       "largura a meia altura e área. Simples e fácil de explicar; perde o resto da curva."),
}
VARIANTES = tuple(INFO_VARIANTES)
# SISSO procura uma fórmula entre combinações dos descritores: faz sentido (e é rápido) com os 6 do pico,
# não com os 100 pontos da curva
SO_PICO = {"sisso"}


# ----------------------------------------------------------------------------- representações
def grade_comum(curvas: list[tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """Potenciais da grade: a faixa coberta por todas as curvas."""
    lo = max(float(np.nanmin(e)) for e, _ in curvas)
    hi = min(float(np.nanmax(e)) for e, _ in curvas)
    if hi - lo < 0.1:
        raise ValueError(f"as curvas não têm uma faixa de potencial em comum (sobra {max(hi - lo, 0):.3f} V); "
                         "confira se são todas da mesma técnica e do mesmo procedimento")
    return np.linspace(lo, hi, N_PONTOS)


def _na_grade(e, i, grade) -> np.ndarray:
    e, i = np.asarray(e, float), np.asarray(i, float)
    ok = np.isfinite(e) & np.isfinite(i)
    ordem = np.argsort(e[ok])
    return np.interp(grade, e[ok][ordem], i[ok][ordem])


def representar(curvas: list[tuple], variante: str, grade: np.ndarray) -> pd.DataFrame:
    """Tabela (uma linha por curva) na representação pedida, com nomes de coluna."""
    if variante == "pico":
        linhas = [medir_pico(e, i) for e, i in curvas]
        return pd.DataFrame([[np.nan if r.get(c) is None else r[c] for c in CAMPOS_PICO] for r in linhas],
                            columns=list(CAMPOS_PICO), dtype=float)
    Y = np.vstack([_na_grade(e, i, grade) for e, i in curvas])
    if variante == "forma":
        amp = np.ptp(Y, axis=1, keepdims=True)
        Y = (Y - Y.min(axis=1, keepdims=True)) / np.where(amp > 0, amp, 1)
    elif variante == "derivada":
        from scipy.signal import savgol_filter
        Y = savgol_filter(Y, 11, 3, deriv=1, axis=1)
    elif variante in ("base_vales", "base_als"):
        Y = np.vstack([y - linha_base(grade, y, variante.split("_")[1]) for y in Y])
    elif variante != "curva":
        raise ValueError(f"representação desconhecida: {variante}")
    return pd.DataFrame(Y, columns=[f"{variante}_{e:+.3f}V" for e in grade])


# ----------------------------------------------------------------------------- métricas
def metricas(y, proba, limiar: float = 0.5) -> dict:
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score
    y, proba = np.asarray(y, int), np.asarray(proba, float)
    prev = (proba >= limiar).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, prev, labels=[0, 1]).ravel()
    return {"n": int(len(y)), "balanced_accuracy": float(balanced_accuracy_score(y, prev)),
            "acuracia": float((prev == y).mean()),
            "sensibilidade": float(tp / (tp + fn)) if tp + fn else None,
            "especificidade": float(tn / (tn + fp)) if tn + fp else None,
            "roc_auc": float(roc_auc_score(y, proba)) if len(set(y)) == 2 else None,
            "matriz_confusao": [[int(tn), int(fp)], [int(fn), int(tp)]]}


def _proba(modelo, X) -> np.ndarray:
    return modelo.predict_proba(X)[:, list(modelo.classes_).index(1)]


def _fora_da_dobra(modelo, X, y, dobras) -> np.ndarray:
    """Probabilidade de cada medição prevista por um modelo que não a viu."""
    from sklearn.base import clone
    p = np.full(len(y), np.nan)
    for tr, te in dobras:
        if len(set(y[tr])) < 2:                       # dobra de treino com uma classe só
            p[te] = float(y[tr][0])
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p[te] = _proba(clone(modelo).fit(X.iloc[tr], y[tr]), X.iloc[te])
    return p


# ----------------------------------------------------------------------------- dados
def dados_de_treino(df: pd.DataFrame) -> pd.DataFrame:
    """Ensaios que entram no treino (precisa das colunas potential_v e current_ua)."""
    d = df[(df["qc_flag"].fillna("PASS") != "FAIL") & df["tipo"].isin(["branco", "rna"])]
    d = d[d["potential_v"].map(lambda v: isinstance(v, list) and len(v) >= 20)]
    return d.reset_index(drop=True)


def _dividir(y, grupos, seed) -> tuple[np.ndarray, np.ndarray, str | None]:
    """(índices de treino, de teste, aviso). Sem eletrodos suficientes: teste vazio e um aviso."""
    from sklearn.model_selection import StratifiedGroupKFold
    n_grupos = len(set(grupos))
    tudo = np.arange(len(y))
    if n_grupos >= MIN_ELETRODOS_TESTE:
        for tr, te in StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=seed).split(tudo, y, grupos):
            if len(set(y[te])) == 2 and min(np.bincount(y[tr], minlength=2)) >= MIN_POR_CLASSE:
                return tr, te, None
    return tudo, np.array([], int), (f"sem teste independente: são {n_grupos} eletrodo(s) e é preciso pelo menos "
                                     f"{MIN_ELETRODOS_TESTE} com branco e RNA para guardar uma parte; o resultado é "
                                     "o da validação cruzada, que tende a ser otimista")


def _dobras(y, grupos, seed) -> tuple[list, str]:
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
    n_grupos = len(set(grupos))
    if n_grupos >= 3:
        k = min(5, n_grupos)
        d = list(StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed).split(y, y, grupos))
        return d, f"validação cruzada por eletrodo ({k} partes)"
    k = max(2, min(5, int(np.bincount(y, minlength=2).min())))
    d = list(StratifiedKFold(n_splits=k, shuffle=True, random_state=seed).split(y, y))
    return d, (f"validação cruzada por medição ({k} partes): há só {n_grupos} eletrodo(s), então medições do "
               "mesmo eletrodo caem dos dois lados e o resultado é otimista")


# ----------------------------------------------------------------------------- treino
def treinar(df: pd.DataFrame, algoritmos: list[str] | None = None, variantes: list[str] | None = None,
            seed: int = 42, rapido: bool = False, progresso=None) -> dict:
    """Compara representações × algoritmos e devolve o pacote do melhor (ainda não salvo; ver `salvar`).

    `df`: `genossensor.tabela(s, incluir_curvas=True)`. Erro (ValueError) se faltarem dados."""
    from sklearn.base import clone
    if df.empty:
        raise ValueError("a base está vazia: importe os .nox de branco e de RNA primeiro (fiep rna importar)")
    d = dados_de_treino(df)
    y = (d["tipo"] == "rna").to_numpy(int)
    n_branco, n_rna = int((y == 0).sum()), int((y == 1).sum())
    if min(n_branco, n_rna) < MIN_POR_CLASSE:
        raise ValueError(f"precisa de pelo menos {MIN_POR_CLASSE} medições de branco e {MIN_POR_CLASSE} de RNA "
                         f"aprovadas; hoje há {n_branco} de branco e {n_rna} de RNA")
    grupos = d["eletrodo_id"].astype(str).to_numpy()
    cat = classificadores(seed=seed, rapido=rapido)
    algoritmos = [a for a in (algoritmos or list(cat)) if a in cat]
    variantes = [v for v in (variantes or VARIANTES) if v in INFO_VARIANTES]
    if not algoritmos or not variantes:
        raise ValueError("nenhum algoritmo ou representação válida escolhida")
    tr, te, aviso_teste = _dividir(y, grupos, seed)
    curvas = list(zip(d["potential_v"], d["current_ua"]))
    grade = grade_comum([curvas[k] for k in tr])
    dobras, validacao = _dobras(y[tr], grupos[tr], seed)

    pares = [(v, a) for v in variantes for a in algoritmos if a not in SO_PICO or v == "pico"]
    if not pares:
        raise ValueError("SISSO só roda com a representação 'pico'")
    linhas, X, v_atual = [], None, None
    for feitos, (v, a) in enumerate(pares):
        if v != v_atual:
            X, v_atual = representar(curvas, v, grade), v
        if progresso:
            progresso(f"{INFO_VARIANTES[v]['nome']} · {nome_classificador(a)}", feitos / len(pares))
        try:
            p = _fora_da_dobra(cat[a], X.iloc[tr], y[tr], dobras)
            m = metricas(y[tr], p)
            linhas.append({"representacao": v, "algoritmo": a, **{k: m[k] for k in (
                "balanced_accuracy", "roc_auc", "sensibilidade", "especificidade")}, "erro": None})
        except Exception as ex:  # noqa: BLE001 — um algoritmo que falha não derruba a comparação
            linhas.append({"representacao": v, "algoritmo": a, "balanced_accuracy": None, "roc_auc": None,
                           "sensibilidade": None, "especificidade": None, "erro": str(ex)[:200]})
    ordem_a = {a: k for k, a in enumerate(cat)}
    ordem_v = {v: k for k, v in enumerate(VARIANTES)}
    placar = pd.DataFrame(linhas)
    placar["_ba"] = placar["balanced_accuracy"].fillna(-1)
    placar["_auc"] = placar["roc_auc"].fillna(-1)
    placar = placar.sort_values(["_ba", "_auc", "representacao", "algoritmo"], ascending=[False, False, True, True],
                                key=lambda c: c.map(ordem_v) if c.name == "representacao" else
                                (c.map(ordem_a) if c.name == "algoritmo" else c)).drop(columns=["_ba", "_auc"])
    placar.insert(0, "posicao", range(1, len(placar) + 1))
    melhor = placar.iloc[0]
    if melhor["balanced_accuracy"] is None or pd.isna(melhor["balanced_accuracy"]):
        raise ValueError("nenhum algoritmo conseguiu treinar: " + str(melhor["erro"]))
    v, a = melhor["representacao"], melhor["algoritmo"]
    if progresso:
        progresso("retreinando o escolhido", 0.97)
    X = representar(curvas, v, grade)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        estimador = clone(cat[a]).fit(X.iloc[tr], y[tr])
    m_cv = {k: (None if pd.isna(melhor[k]) else float(melhor[k]))
            for k in ("balanced_accuracy", "roc_auc", "sensibilidade", "especificidade")}
    m_teste = metricas(y[te], _proba(estimador, X.iloc[te])) if len(te) else None
    ref = m_teste or m_cv
    agora = dt.datetime.now().astimezone()
    cartao = {
        "id": agora.strftime("%Y%m%d-%H%M%S"), "criado_em": agora.isoformat(timespec="seconds"),
        "versao": __version__, "seed": seed,
        "algoritmo": a, "algoritmo_nome": nome_classificador(a),
        "representacao": v, "representacao_nome": INFO_VARIANTES[v]["nome"],
        "grade": {"inicio_v": float(grade[0]), "fim_v": float(grade[-1]), "pontos": N_PONTOS},
        "dados": {"n_ensaios": int(len(d)), "n_branco": n_branco, "n_rna": n_rna,
                  "n_eletrodos": int(len(set(grupos))), "n_treino": int(len(tr)), "n_teste": int(len(te)),
                  "eletrodos_teste": sorted(set(grupos[te])),
                  "concentracoes_ng_ml": sorted(float(c) for c in d.loc[d["tipo"] == "rna", "concentracao"].unique())},
        "validacao": validacao, "metricas_cv": m_cv, "metricas_teste": m_teste,
        "referencia": "teste" if m_teste else "validação cruzada",
        "ab_referencia": ref["balanced_accuracy"],
        "confiavel": bool(ref["balanced_accuracy"] is not None and ref["balanced_accuracy"] >= BA_CONFIAVEL),
        "avisos": [x for x in (aviso_teste,) if x],
        "placar": json.loads(placar.to_json(orient="records")),
    }
    return {"estimador": estimador, "representacao": v, "grade": grade, "cartao": cartao}


# ----------------------------------------------------------------------------- registro
def salvar(pacote: dict, pasta: str | Path = PASTA_MODELOS, ativar: bool = True, s=None) -> Path:
    """Grava `modelos/<id>/` (modelo.joblib + cartao.json), marca como em uso e registra no banco (se `s`)."""
    import joblib
    c = pacote["cartao"]
    destino = Path(pasta) / c["id"]
    destino.mkdir(parents=True, exist_ok=True)
    joblib.dump(pacote, destino / "modelo.joblib")
    (destino / "cartao.json").write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    if ativar:
        ativar_modelo(c["id"], pasta)
    if s is not None:
        registrar_modelo(s, c, destino)
        s.commit()
    return destino


def _formato_atual(c: dict) -> bool:
    """Cartões de versões antigas (da época do case, antes da base de RNA) não têm estes campos."""
    return all(k in c for k in ("algoritmo", "representacao", "dados", "placar"))


def em_uso(pasta: str | Path = PASTA_MODELOS) -> str | None:
    """Id do modelo em uso; None se não houver ou se for de uma versão antiga."""
    f = Path(pasta) / "ATUAL"
    id_ = f.read_text(encoding="utf-8").strip() if f.exists() else ""
    c = Path(pasta) / id_ / "cartao.json"
    if not id_ or (c.exists() and not _formato_atual(json.loads(c.read_text(encoding="utf-8")))):
        return None
    return id_


def ativar_modelo(id_: str, pasta: str | Path = PASTA_MODELOS) -> None:
    if not (Path(pasta) / id_ / "modelo.joblib").exists():
        raise FileNotFoundError(f"modelo {id_} não encontrado em {pasta}/")
    cartao(id_, pasta)                    # recusa modelo de versão antiga
    (Path(pasta) / "ATUAL").write_text(id_, encoding="utf-8")


def cartao(id_: str, pasta: str | Path = PASTA_MODELOS) -> dict:
    f = Path(pasta) / id_ / "cartao.json"
    if not f.exists():
        raise FileNotFoundError(f"modelo {id_} não encontrado em {pasta}/")
    c = json.loads(f.read_text(encoding="utf-8"))
    if not _formato_atual(c):
        raise FileNotFoundError(f"modelo {id_} é de uma versão antiga do sistema (antes da base de RNA): "
                                "treine um novo")
    return c


def listar(pasta: str | Path = PASTA_MODELOS) -> list[dict]:
    """Cartões dos modelos salvos, do mais novo ao mais antigo, com `em_uso` (os de versões antigas ficam de fora)."""
    atual = em_uso(pasta)
    cs = [json.loads(f.read_text(encoding="utf-8")) for f in Path(pasta).glob("*/cartao.json")]
    cs = [c for c in cs if _formato_atual(c)]
    return [{**c, "em_uso": c["id"] == atual} for c in sorted(cs, key=lambda c: c["id"], reverse=True)]


def carregar(pasta: str | Path = PASTA_MODELOS, id_: str | None = None) -> dict:
    import joblib
    id_ = id_ or em_uso(pasta)
    if not id_:
        raise FileNotFoundError(f"nenhum modelo em uso em {pasta}/: treine com `fiep rna treinar`")
    f = Path(pasta) / id_ / "modelo.joblib"
    if not f.exists():
        raise FileNotFoundError(f"modelo {id_} não encontrado em {pasta}/")
    return joblib.load(f)


# ----------------------------------------------------------------------------- previsão
def prever_curva(pacote: dict, e, i) -> dict:
    """Resultado de uma curva: resultado, prob_contaminado e motivo."""
    e = np.asarray(e, float)
    grade, c = pacote["grade"], pacote["cartao"]
    if np.isfinite(e).sum() < 20:
        return {"resultado": "REPETIR MEDIÇÃO", "prob_contaminado": None, "motivo": "curva com menos de 20 pontos"}
    lo, hi = float(np.nanmin(e)), float(np.nanmax(e))
    if lo > grade[0] + TOLERANCIA_V or hi < grade[-1] - TOLERANCIA_V:
        return {"resultado": "REPETIR MEDIÇÃO", "prob_contaminado": None,
                "motivo": f"a curva vai de {lo:.3f} a {hi:.3f} V e o modelo precisa de {grade[0]:.3f} a "
                          f"{grade[-1]:.3f} V (mesmo procedimento do treino)"}
    X = representar([(e, i)], pacote["representacao"], grade)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = float(_proba(pacote["estimador"], X)[0])
    if not c["confiavel"]:
        return {"resultado": "INCONCLUSIVO", "prob_contaminado": p,
                "motivo": f"o modelo ainda não é confiável: acurácia balanceada de {c['ab_referencia']:.2f} "
                          f"({c['referencia']}), abaixo de {BA_CONFIAVEL}"}
    return {"resultado": "CONTAMINADO" if p >= 0.5 else "NÃO CONTAMINADO", "prob_contaminado": p, "motivo": None}


def prever_arquivos(pacote: dict, arquivos: list[str | Path]) -> list[dict]:
    """Um resultado por .nox, com o pico, a curva e o que o nome do arquivo diz (se diz)."""
    from .genossensor import ler_arquivo
    saida = []
    for a in arquivos:
        a = Path(a)
        try:
            r = ler_arquivo(a)
        except Exception as ex:  # noqa: BLE001
            saida.append({"arquivo": a.name, "resultado": "REPETIR MEDIÇÃO", "prob_contaminado": None,
                          "motivo": f"não foi possível ler o arquivo ({ex})"})
            continue
        res = prever_curva(pacote, r["potential_v"], r["current_ua"])
        saida.append({"arquivo": a.name, "sha256": r["sha256"], "eletrodo_id": r.get("eletrodo_id"),
                      "tipo_informado": r["tipo"] if r.get("tipo") in ("branco", "rna") else None,
                      "concentracao_informada": r.get("concentracao") if r.get("tipo") == "rna" else None,
                      **res, **{k: r.get(k) for k in CAMPOS_PICO},
                      "potential_v": r["potential_v"], "current_ua": r["current_ua"]})
    return saida


def registrar_modelo(s, c: dict, caminho: str | Path | None = None) -> None:
    """Linha do modelo na tabela `modelos` (idempotente)."""
    from .orm import ModeloML
    s.merge(ModeloML(id=c["id"], algoritmo=c["algoritmo"], representacao=c["representacao"],
                     balanced_accuracy=c["ab_referencia"], referencia=c["referencia"],
                     n_ensaios=c["dados"]["n_ensaios"], caminho=str(caminho) if caminho else None, cartao=c))
    s.flush()


def gravar_predicoes(s, resultados: list[dict], cartao_modelo: dict, usuario_id: int | None = None) -> int:
    from .orm import ModeloML, Predicao
    if s.get(ModeloML, cartao_modelo["id"]) is None:
        registrar_modelo(s, cartao_modelo)
    for r in resultados:
        s.add(Predicao(modelo_id=cartao_modelo["id"], arquivo=r.get("arquivo"), sha256=r.get("sha256"),
                       eletrodo_id=r.get("eletrodo_id"), resultado=r["resultado"],
                       prob_contaminado=r.get("prob_contaminado"), motivo=r.get("motivo"),
                       tipo_informado=r.get("tipo_informado"), usuario_id=usuario_id))
    s.commit()
    return len(resultados)
