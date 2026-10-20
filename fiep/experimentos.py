"""Experimentos: comparar variantes de features x modelos e escolher o melhor de forma honesta.

Protocolo (o mesmo descrito no artigo), com três conjuntos separados por AMOSTRA
(ver `fiep/divisao.py`; padrão 50/25/25 — Hastie et al., *Elements of Statistical Learning*, 7.2):

1. **Treino**: cada combinação variante x modelo é ajustada no treino. A validação cruzada
   agrupada (StratifiedGroupKFold por `sample_id`) no treino dá a estabilidade (média ± desvio) e o
   limiar de decisão (J de Youden nas previsões fora da dobra).
2. **Validação**: o modelo treinado no treino classifica a validação com aquele limiar; a
   combinação escolhida é a de maior acurácia balanceada na validação (desempate: AUC na
   validação e acurácia da validação cruzada).
3. **Teste**: só depois da escolha, cada combinação é re-treinada com treino + validação e
   avaliada uma vez no teste. O número que vale é o do teste da combinação escolhida — o
   teste nunca é usado para escolher modelo, limiar ou grade de potencial.
4. **Regressão da carga** (log10 UFC/mL) nas amostras contaminadas, com o mesmo protocolo
   (escolha pelo RMSE na validação).
5. O modelo escolhido (treino + validação) e o melhor regressor são salvos em `modelos/` e
   passam a ser os usados pela API. Tabelas, figuras e números do artigo vão para a pasta do experimento.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import (balanced_accuracy_score, mean_absolute_error, mean_squared_error, r2_score)
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold

from .catalogo import classificadores, regressores
from .config import _merge
from .features import colunas_features
from .divisao import Divisao, montar
from .divisao import subconjunto as _sub
from .ingest import Dataset, juntar
from .model import _impressao_dados, _metricas, limiar_youden, montar_tabela, salvar_pacote

log = logging.getLogger(__name__)

VARIANTES = {
    "dif_resumo": {"features": {"modo": "diferenca_estagios", "curva_delta_completa": False}},
    "dif_curva": {"features": {"modo": "diferenca_estagios", "curva_delta_completa": True}},
    "dif_curva_linha_base": {"features": {"modo": "diferenca_estagios", "curva_delta_completa": True},
                             "preprocessamento": {"linha_de_base": "linear_extremos"}},
    "dif_curva_sem_suavizar": {"features": {"modo": "diferenca_estagios", "curva_delta_completa": True},
                               "preprocessamento": {"suavizar": False}},
    "estagio_final": {"features": {"modo": "estagio_unico"}},
}
DESCRICAO_VARIANTES = {
    "dif_resumo": "descritores de pico por estágio + diferenças entre estágios",
    "dif_curva": "idem + curva de diferença completa (último − penúltimo estágio)",
    "dif_curva_linha_base": "dif_curva com linha de base linear removida",
    "dif_curva_sem_suavizar": "dif_curva sem suavização Savitzky-Golay",
    "estagio_final": "só o estágio final do sensor (sem diferença entre estágios)",
}
ROTULO = "contamination_status"
ALVO_REG = "sample_log10_mean_cfu_ml"


# ----------------------------------------------------------------------------- dados

def subconjunto(ds: Dataset, amostras) -> Dataset:
    """Mantido por compatibilidade; ver `fiep.divisao.subconjunto`."""
    return _sub(ds, amostras)


def _tabelas(div: Divisao, cfg_v: dict):
    """Tabelas de features dos três conjuntos; a grade de potencial vem só do treino."""
    tab_tr, grade, qc_tr = montar_tabela(div.treino, cfg_v)
    if tab_tr.empty or ROTULO not in tab_tr:
        raise ValueError("nenhuma réplica completa no treino")
    out, qcs = {"treino": tab_tr}, [qc_tr]
    for k in ("validacao", "teste"):
        out[k] = pd.DataFrame()
        if div[k] is not None:
            try:
                out[k], _, q = montar_tabela(div[k], cfg_v, grade=grade)
                qcs.append(q)
            except ValueError:
                pass
        if len(out[k]) and ROTULO in out[k]:
            out[k] = out[k].dropna(subset=[ROTULO])
        else:
            out[k] = pd.DataFrame()
    out["treino"] = tab_tr.dropna(subset=[ROTULO])
    return out, grade, pd.concat(qcs, ignore_index=True)


# ----------------------------------------------------------------------------- classificação

def _cv_classificacao(est, X, y, grupos, n_folds, seed):
    cv = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    proba = np.full(len(y), np.nan)
    ba_dobras = []
    for tr, te in cv.split(X, y, grupos):
        m = clone(est).fit(X.iloc[tr], y[tr])
        proba[te] = m.predict_proba(X.iloc[te])[:, 1]
        ba_dobras.append(balanced_accuracy_score(y[te], (proba[te] >= 0.5).astype(int)))
    lim = limiar_youden(y, proba)
    met = _metricas(y, proba, lim)
    return proba, lim, met, float(np.std(ba_dobras))


def _xy(tab: pd.DataFrame, feats: list[str]):
    X = tab.reindex(columns=feats).astype(float)
    y = tab[ROTULO].astype(int).to_numpy()
    g = tab["sample_id"].astype(str).to_numpy()
    return X, y, g


# ----------------------------------------------------------------------------- regressão

def _cv_regressao(est, X, y, grupos, n_folds):
    n = min(n_folds, len(set(grupos)))
    pred = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=n).split(X, y, grupos):
        m = clone(est).fit(X.iloc[tr], y[tr])
        pred[te] = np.ravel(m.predict(X.iloc[te]))
    return pred


def _met_reg(y, p):
    return {"rmse": float(np.sqrt(mean_squared_error(y, p))), "mae": float(mean_absolute_error(y, p)),
            "r2": float(r2_score(y, p)) if len(y) > 1 else np.nan}


# ----------------------------------------------------------------------------- execução

def _impressao(div: Divisao) -> str:
    """Impressão digital dos dados E da divisão (outra divisão = outro experimento)."""
    import hashlib
    partes = [f"{k}:{_impressao_dados(div[k]) if div[k] is not None else '-'}" for k in ("treino", "validacao", "teste")]
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:16]


def _fmt(x):
    return f"{x:.3f}" if isinstance(x, (int, float)) and np.isfinite(x) else "--"


def rodar(dados: Divisao | Dataset, cfg: dict, saida: str | Path = "resultados",
          pasta_modelos: str | Path = "modelos", variantes: list[str] | None = None, rapido: bool = False,
          registrar: bool = True) -> dict:
    """Roda o experimento. `dados` é uma Divisao (treino/validação/teste) ou um Dataset único,
    que então é dividido nas proporções de `[divisao]` da configuração."""
    div = dados if isinstance(dados, Divisao) else montar(dados, {}, cfg)
    seed = cfg["modelo"]["seed"]
    n_folds = cfg["modelo"]["n_folds"]
    exp_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    pasta = Path(saida) / exp_id
    pasta.mkdir(parents=True, exist_ok=True)

    variantes = variantes or (["dif_resumo", "dif_curva"] if rapido else list(VARIANTES))
    modelos = classificadores(seed, rapido=rapido)
    linhas, prob_teste, tabelas = [], {}, {}

    for v in variantes:
        cfg_v = _merge(copy.deepcopy(cfg), VARIANTES[v])
        try:
            tabs, grade, qc = _tabelas(div, cfg_v)
        except ValueError as e:
            log.warning("Variante %s ignorada: %s", v, e)
            continue
        tab_tr, tab_va, tab_te = tabs["treino"], tabs["validacao"], tabs["teste"]
        feats = colunas_features(tab_tr)
        X, y, g = _xy(tab_tr, feats)
        k = min(n_folds, len(set(g)), int(np.bincount(y).min())) if len(np.unique(y)) == 2 else 0
        if k < 2:
            log.warning("Variante %s: dados insuficientes para CV", v)
            continue
        tab_trva = pd.concat([tab_tr, tab_va], ignore_index=True) if len(tab_va) else tab_tr
        tabelas[v] = (tab_tr, tab_va, tab_te, grade, feats, cfg_v, qc)
        for nome, est in modelos.items():
            try:
                proba, lim, met, dp = _cv_classificacao(est, X, y, g, k, seed)
                linha = {"variante": v, "modelo": nome, "n_treino": len(y), "n_features": len(feats),
                         "cv_balanced_accuracy": met["balanced_accuracy"], "cv_ba_desvio": dp,
                         "cv_sensibilidade": met["sensibilidade"], "cv_especificidade": met["especificidade"],
                         "cv_roc_auc": met["roc_auc"], "limiar": lim}
                if len(tab_va):                 # escolha: modelo do treino na validação
                    Xv, yv, _ = _xy(tab_va, feats)
                    mv = _metricas(yv, clone(est).fit(X, y).predict_proba(Xv)[:, 1], lim)
                    linha.update({"n_validacao": len(yv), "val_balanced_accuracy": mv["balanced_accuracy"],
                                  "val_sensibilidade": mv["sensibilidade"], "val_especificidade": mv["especificidade"],
                                  "val_roc_auc": mv["roc_auc"]})
                if len(tab_te):                 # avaliação: re-treinado com treino + validação
                    Xa, ya, _ = _xy(tab_trva, feats)
                    Xt, yt, _ = _xy(tab_te, feats)
                    pt = clone(est).fit(Xa, ya).predict_proba(Xt)[:, 1]
                    mt = _metricas(yt, pt, lim)
                    linha.update({"n_teste": len(yt), "teste_balanced_accuracy": mt["balanced_accuracy"],
                                  "teste_sensibilidade": mt["sensibilidade"], "teste_especificidade": mt["especificidade"],
                                  "teste_roc_auc": mt["roc_auc"], "teste_vp": mt["vp"], "teste_fp": mt["fp"],
                                  "teste_vn": mt["vn"], "teste_fn": mt["fn"]})
                    prob_teste[(v, nome)] = (yt, pt)
            except Exception as e:  # noqa: BLE001 - um modelo que falha não derruba o experimento
                log.warning("%s/%s falhou: %s", v, nome, e)
                continue
            linhas.append(linha)
            log.info("%-22s %-14s CV BA=%.3f±%.3f  val BA=%s  teste BA=%s", v, nome, met["balanced_accuracy"], dp,
                     _fmt(linha.get("val_balanced_accuracy")), _fmt(linha.get("teste_balanced_accuracy")))

    if not linhas:
        from .divisao import diagnosticar
        raise ValueError("Nenhuma combinação pôde ser avaliada.\n" + diagnosticar(juntar(div.treino, div.validacao), cfg))
    placar = pd.DataFrame(linhas)
    usa_val = "val_balanced_accuracy" in placar and placar["val_balanced_accuracy"].notna().any() \
        and placar["val_roc_auc"].notna().any()
    ordem = ["val_balanced_accuracy", "val_roc_auc", "cv_balanced_accuracy", "cv_roc_auc"] if usa_val \
        else ["cv_balanced_accuracy", "cv_roc_auc"]
    if not usa_val:
        log.warning("Validação sem as duas classes: a escolha usa a validação cruzada no treino.")
    placar = placar.sort_values(ordem, ascending=False, na_position="last").reset_index(drop=True)
    placar.insert(0, "posicao", range(1, len(placar) + 1))
    placar.to_csv(pasta / "classificacao.csv", index=False)
    if prob_teste:                          # probabilidades no teste: refazer figuras sem retreinar
        pd.concat([pd.DataFrame({"variante": v, "modelo": m, "y": y, "prob": p})
                   for (v, m), (y, p) in prob_teste.items()]).to_csv(pasta / "probabilidades_teste.csv", index=False)
    melhor = placar.iloc[0]
    v_best, m_best = melhor["variante"], melhor["modelo"]
    tab_tr, tab_va, tab_te, grade, feats, cfg_best, qc = tabelas[v_best]
    tab_trva = pd.concat([tab_tr, tab_va], ignore_index=True) if len(tab_va) else tab_tr
    X, y, g = _xy(tab_trva, feats)
    final = clone(modelos[m_best]).fit(X, y)          # modelo final: treino + validação
    formula = final.formula() if hasattr(final, "formula") else None
    sisso_formula = None
    sisso_rows = placar[placar["modelo"] == "sisso"]
    if len(sisso_rows):
        vs = sisso_rows.iloc[0]["variante"]
        t = tabelas[vs]
        ts = pd.concat([t[0], t[1]], ignore_index=True) if len(t[1]) else t[0]
        Xs, ys, _ = _xy(ts, t[4])
        sisso_formula = clone(modelos["sisso"]).fit(Xs, ys).formula()

    # ---------------- regressão da carga nas contaminadas
    def contaminadas(t):
        return t[(t[ROTULO] == 1) & t[ALVO_REG].notna()] if len(t) and ALVO_REG in t else pd.DataFrame()

    def xr(t, fts):
        return t.reindex(columns=fts).astype(float), t[ALVO_REG].astype(float).to_numpy()

    reg_linhas, reg_pred, melhor_reg = [], {}, None
    regs = regressores(seed, rapido=rapido)
    for v in dict.fromkeys([v_best, "dif_resumo"]):
        if v not in tabelas:
            continue
        ttr, tva, tte, _, fts, _, _ = tabelas[v]
        rtr, rva, rte = contaminadas(ttr), contaminadas(tva), contaminadas(tte)
        if len(rtr) < 10:
            continue
        Xr, yr = xr(rtr, fts)
        gr = rtr["sample_id"].astype(str).to_numpy()
        rtrva = pd.concat([rtr, rva], ignore_index=True) if len(rva) else rtr
        for nome, est in regs.items():
            try:
                p = _cv_regressao(est, Xr, yr, gr, n_folds)
                linha = {"variante": v, "modelo": nome, "n_treino": len(yr),
                         **{f"cv_{k}": val for k, val in _met_reg(yr, p).items()}}
                if len(rva):
                    Xv, yv = xr(rva, fts)
                    pv = np.ravel(clone(est).fit(Xr, yr).predict(Xv))
                    linha.update({"n_validacao": len(yv), **{f"val_{k}": val for k, val in _met_reg(yv, pv).items()}})
                if len(rte):
                    Xa, ya = xr(rtrva, fts)
                    Xt, yt = xr(rte, fts)
                    pt = np.ravel(clone(est).fit(Xa, ya).predict(Xt))
                    linha.update({"n_teste": len(yt), **{f"teste_{k}": val for k, val in _met_reg(yt, pt).items()}})
                    reg_pred[(v, nome)] = (yt, pt)
            except Exception as e:  # noqa: BLE001
                log.warning("regressão %s/%s falhou: %s", v, nome, e)
                continue
            reg_linhas.append(linha)
    reg = pd.DataFrame(reg_linhas)
    regressor_final = None
    if len(reg):
        chave = ["val_rmse", "cv_rmse"] if "val_rmse" in reg and reg["val_rmse"].notna().any() else ["cv_rmse"]
        reg = reg.sort_values(chave, na_position="last").reset_index(drop=True)
        reg.to_csv(pasta / "regressao.csv", index=False)
        melhor_reg = reg.iloc[0].to_dict()
        # o regressor salvo junto com o classificador usa as MESMAS features (mesma variante)
        r1 = reg[reg["variante"] == v_best]
        if len(r1):
            melhor_reg = r1.iloc[0].to_dict()
            rall = contaminadas(tab_trva)
            regressor_final = clone(regs[r1.iloc[0]["modelo"]]).fit(*xr(rall, feats))

    resumo = {
        "experimento": exp_id,
        "teste": div.descricao(),
        "proporcoes": div.proporcoes,
        "origem": div.origem,
        "criterio_escolha": "acurácia balanceada na validação" if usa_val else "validação cruzada no treino",
        "amostras_treino": int(tab_tr["sample_id"].nunique()),
        "amostras_validacao": int(tab_va["sample_id"].nunique()) if len(tab_va) else 0,
        "amostras_teste": int(tab_te["sample_id"].nunique()) if len(tab_te) else 0,
        "replicas_treino": int(len(tab_tr)), "replicas_validacao": int(len(tab_va)),
        "replicas_teste": int(len(tab_te)),
        "combinacoes_avaliadas": int(len(placar)),
        "melhor": {k: (float(v) if isinstance(v, (np.floating, float)) else (int(v) if isinstance(v, (np.integer,)) else v))
                   for k, v in melhor.items()},
        "descricao_variante": DESCRICAO_VARIANTES.get(v_best, v_best),
        "formula_sisso": sisso_formula,
        "melhor_regressao": melhor_reg,
        "impressao_dados": _impressao(div),
    }

    if registrar:
        todos = juntar(div.treino, div.validacao)
        pasta_m, cartao = salvar_pacote(
            final, feats, grade, cfg_best, float(melhor["limiar"]), f"{m_best} [{v_best}]",
            metricas_cv={"balanced_accuracy": melhor["cv_balanced_accuracy"], "roc_auc": melhor["cv_roc_auc"],
                         "sensibilidade": melhor["cv_sensibilidade"], "especificidade": melhor["cv_especificidade"]},
            info={"n_amostras": int(tab_trva["sample_id"].nunique()), "n_linhas": int(len(tab_trva)),
                  "impressao_dados": _impressao_dados(todos)},
            pasta_modelos=pasta_modelos,
            extras={"experimento": exp_id, "variante": v_best, "divisao": resumo["teste"],
                    "metricas_validacao": {k.replace("val_", ""): melhor[k] for k in melhor.index
                                           if k.startswith("val_")},
                    "metricas_teste": {k.replace("teste_", ""): melhor[k] for k in melhor.index
                                       if k.startswith("teste_")},
                    "formula": formula, "regressor": melhor_reg["modelo"] if regressor_final is not None else None},
            adicionais={"regressor": regressor_final})
        resumo["modelo_registrado"] = cartao["id"]

    (pasta / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    from . import figuras
    figuras.gerar_todas(pasta, placar, prob_teste, (v_best, m_best), tabelas, reg, reg_pred, final, resumo)
    log.info("Experimento %s: melhor = %s/%s (val BA %s; teste BA %s)", exp_id, v_best, m_best,
             _fmt(melhor.get("val_balanced_accuracy")), _fmt(melhor.get("teste_balanced_accuracy")))
    return {"pasta": pasta, "placar": placar, "regressao": reg, "resumo": resumo, "modelo_final": final,
            "divisao": div}


def ultimo_experimento(dados: Divisao | Dataset, saida: str | Path = "resultados", cfg: dict | None = None) -> dict | None:
    """Último experimento já rodado com exatamente estes dados e esta divisão, ou None."""
    base = Path(saida)
    if not base.exists():
        return None
    div = dados if isinstance(dados, Divisao) else montar(dados, {}, cfg)
    alvo = _impressao(div)
    for pasta in sorted((p for p in base.iterdir() if (p / "resumo.json").exists()), reverse=True):
        resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
        if resumo.get("impressao_dados") == alvo:
            reg = pd.read_csv(pasta / "regressao.csv") if (pasta / "regressao.csv").exists() else pd.DataFrame()
            return {"pasta": pasta, "placar": pd.read_csv(pasta / "classificacao.csv"), "regressao": reg,
                    "resumo": resumo, "reaproveitado": True, "divisao": div}
    return None
