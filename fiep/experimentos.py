"""Experimentos: comparar variantes de features x modelos e escolher o melhor de forma honesta.

Protocolo (o mesmo descrito no artigo):

1. **Conjunto de teste separado antes de tudo.** Se houver `dados/validacao/`, ele é o teste
   (validação externa). Senão, 20% das AMOSTRAS (estratificado pela classe) ficam de fora.
   Nada do teste é usado para escolher modelo, limiar ou grade de potencial.
2. **Seleção por validação cruzada agrupada** (StratifiedGroupKFold por `sample_id`) só no treino:
   cada combinação variante x modelo recebe a acurácia balanceada média das dobras e o desvio.
   O limiar de decisão vem das previsões fora da dobra (J de Youden).
3. **Avaliação no teste** de todas as combinações (para a tabela do artigo), mas o modelo
   "escolhido" é o melhor da validação cruzada — não o melhor do teste.
4. **Regressão da carga** (log10 UFC/mL) nas amostras contaminadas, com o mesmo protocolo.
5. O modelo escolhido (+ o melhor regressor) é salvo em `modelos/` e passa a ser o usado pela
   API. Tabelas, figuras e números do artigo vão para a pasta do experimento.
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
from .ingest import Dataset
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
    amostras = set(amostras)
    med = ds.medicoes[ds.medicoes["sample_id"].isin(amostras)]
    ids = set(med["measurement_id"])
    return Dataset(med, ds.pontos[ds.pontos["measurement_id"].isin(ids)],
                   ds.amostras[ds.amostras["sample_id"].isin(amostras)] if len(ds.amostras) else ds.amostras,
                   ds.relatorio, ds.plaqueamento, ds.arquivos)


def separar_teste(ds: Dataset, frac: float = 0.2, seed: int = 42):
    """Amostras de teste estratificadas pela classe (nível de amostra)."""
    am = (ds.medicoes.dropna(subset=["sample_id", ROTULO]).groupby("sample_id")[ROTULO].max()
          .astype(int).reset_index())
    n = max(2, int(round(1 / frac)))
    cv = StratifiedGroupKFold(n_splits=n, shuffle=True, random_state=seed)
    _, te = next(cv.split(am, am[ROTULO], am["sample_id"]))
    teste = set(am.iloc[te]["sample_id"])
    return set(am["sample_id"]) - teste, teste


def _tabelas(ds_tr: Dataset, ds_te: Dataset, cfg_v: dict):
    tab_tr, grade, qc_tr = montar_tabela(ds_tr, cfg_v)
    try:
        tab_te, _, qc_te = montar_tabela(ds_te, cfg_v, grade=grade)
    except ValueError:
        tab_te, qc_te = pd.DataFrame(), pd.DataFrame()
    return tab_tr, tab_te, grade, pd.concat([qc_tr, qc_te], ignore_index=True)


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

def rodar(ds_treino: Dataset, cfg: dict, ds_validacao: Dataset | None = None, saida: str | Path = "resultados",
          pasta_modelos: str | Path = "modelos", variantes: list[str] | None = None, rapido: bool = False,
          registrar: bool = True, frac_teste: float = 0.2) -> dict:
    seed = cfg["modelo"]["seed"]
    n_folds = cfg["modelo"]["n_folds"]
    exp_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    pasta = Path(saida) / exp_id
    pasta.mkdir(parents=True, exist_ok=True)

    if ds_validacao is not None:
        ds_tr, ds_te, tipo_teste = ds_treino, ds_validacao, "validação externa (dados/validacao)"
    else:
        am_tr, am_te = separar_teste(ds_treino, frac_teste, seed)
        ds_tr, ds_te = subconjunto(ds_treino, am_tr), subconjunto(ds_treino, am_te)
        tipo_teste = f"{int(frac_teste * 100)}% das amostras separadas antes do treino (estratificado)"

    variantes = variantes or (["dif_resumo", "dif_curva"] if rapido else list(VARIANTES))
    modelos = classificadores(seed, rapido=rapido)
    linhas, prob_teste, tabelas = [], {}, {}

    for v in variantes:
        cfg_v = _merge(copy.deepcopy(cfg), VARIANTES[v])
        try:
            tab_tr, tab_te, grade, qc = _tabelas(ds_tr, ds_te, cfg_v)
        except ValueError as e:
            log.warning("Variante %s ignorada: %s", v, e)
            continue
        tab_tr = tab_tr.dropna(subset=[ROTULO])
        tab_te = tab_te.dropna(subset=[ROTULO]) if len(tab_te) else tab_te
        feats = colunas_features(tab_tr)
        X, y, g = _xy(tab_tr, feats)
        k = min(n_folds, len(set(g)), int(np.bincount(y).min()))
        if k < 2:
            log.warning("Variante %s: dados insuficientes para CV", v)
            continue
        tabelas[v] = (tab_tr, tab_te, grade, feats, cfg_v, qc)
        for nome, est in modelos.items():
            try:
                proba, lim, met, dp = _cv_classificacao(est, X, y, g, k, seed)
            except Exception as e:  # noqa: BLE001 - um modelo que falha não derruba o experimento
                log.warning("%s/%s falhou na CV: %s", v, nome, e)
                continue
            linha = {"variante": v, "modelo": nome, "n_treino": len(y), "n_features": len(feats),
                     "cv_balanced_accuracy": met["balanced_accuracy"], "cv_ba_desvio": dp,
                     "cv_sensibilidade": met["sensibilidade"], "cv_especificidade": met["especificidade"],
                     "cv_roc_auc": met["roc_auc"], "limiar": lim}
            if len(tab_te):
                Xt, yt, _ = _xy(tab_te, feats)
                m = clone(est).fit(X, y)
                pt = m.predict_proba(Xt)[:, 1]
                mt = _metricas(yt, pt, lim)
                linha.update({"n_teste": len(yt), "teste_balanced_accuracy": mt["balanced_accuracy"],
                              "teste_sensibilidade": mt["sensibilidade"], "teste_especificidade": mt["especificidade"],
                              "teste_roc_auc": mt["roc_auc"], "teste_vp": mt["vp"], "teste_fp": mt["fp"],
                              "teste_vn": mt["vn"], "teste_fn": mt["fn"]})
                prob_teste[(v, nome)] = (yt, pt)
            linhas.append(linha)
            log.info("%-22s %-14s CV BA=%.3f±%.3f  teste BA=%s", v, nome, met["balanced_accuracy"], dp,
                     f"{linha.get('teste_balanced_accuracy', float('nan')):.3f}")

    if not linhas:
        raise ValueError("Nenhuma combinação pôde ser avaliada (verifique rótulos e estágios do sensor).")
    placar = (pd.DataFrame(linhas).sort_values(["cv_balanced_accuracy", "cv_roc_auc"], ascending=False)
              .reset_index(drop=True))
    placar.insert(0, "posicao", range(1, len(placar) + 1))
    placar.to_csv(pasta / "classificacao.csv", index=False)
    if prob_teste:                          # probabilidades no teste: refazer figuras sem retreinar
        pd.concat([pd.DataFrame({"variante": v, "modelo": m, "y": y, "prob": p})
                   for (v, m), (y, p) in prob_teste.items()]).to_csv(pasta / "probabilidades_teste.csv", index=False)
    melhor = placar.iloc[0]
    v_best, m_best = melhor["variante"], melhor["modelo"]
    tab_tr, tab_te, grade, feats, cfg_best, qc = tabelas[v_best]
    X, y, g = _xy(tab_tr, feats)
    final = clone(modelos[m_best]).fit(X, y)
    formula = final.formula() if hasattr(final, "formula") else None
    sisso_formula = None
    sisso_rows = placar[placar["modelo"] == "sisso"]
    if len(sisso_rows):
        vs = sisso_rows.iloc[0]["variante"]
        ttr = tabelas[vs][0]
        Xs, ys, _ = _xy(ttr, tabelas[vs][3])
        sisso_formula = clone(modelos["sisso"]).fit(Xs, ys).formula()

    # ---------------- regressão da carga nas contaminadas
    reg_linhas, reg_pred, melhor_reg = [], {}, None
    regs = regressores(seed, rapido=rapido)
    for v in dict.fromkeys([v_best, "dif_resumo"]):
        if v not in tabelas:
            continue
        ttr, tte, _, fts, _, _ = tabelas[v]
        if ALVO_REG not in ttr:
            continue
        rtr = ttr[(ttr[ROTULO] == 1) & ttr[ALVO_REG].notna()]
        if len(rtr) < 10:
            continue
        Xr, yr, gr = rtr.reindex(columns=fts).astype(float), rtr[ALVO_REG].astype(float).to_numpy(), \
            rtr["sample_id"].astype(str).to_numpy()
        rte = tte[(tte[ROTULO] == 1) & tte[ALVO_REG].notna()] if len(tte) and ALVO_REG in tte else pd.DataFrame()
        for nome, est in regs.items():
            p = _cv_regressao(est, Xr, yr, gr, n_folds)
            linha = {"variante": v, "modelo": nome, "n_treino": len(yr),
                     **{f"cv_{k}": val for k, val in _met_reg(yr, p).items()}}
            if len(rte):
                m = clone(est).fit(Xr, yr)
                pt = np.ravel(m.predict(rte.reindex(columns=fts).astype(float)))
                linha.update({"n_teste": len(rte), **{f"teste_{k}": val for k, val in
                                                     _met_reg(rte[ALVO_REG].astype(float).to_numpy(), pt).items()}})
                reg_pred[(v, nome)] = (rte[ALVO_REG].astype(float).to_numpy(), pt)
            reg_linhas.append(linha)
    reg = pd.DataFrame(reg_linhas)
    regressor_final = None
    if len(reg):
        reg = reg.sort_values("cv_rmse").reset_index(drop=True)
        reg.to_csv(pasta / "regressao.csv", index=False)
        melhor_reg = reg.iloc[0].to_dict()
        # o regressor salvo junto com o classificador usa as MESMAS features (mesma variante)
        r1 = reg[reg["variante"] == v_best]
        if len(r1):
            melhor_reg = r1.iloc[0].to_dict()
            ttr = tabelas[v_best][0]
            rtr = ttr[(ttr[ROTULO] == 1) & ttr[ALVO_REG].notna()]
            regressor_final = clone(regs[r1.iloc[0]["modelo"]]).fit(
                rtr.reindex(columns=feats).astype(float), rtr[ALVO_REG].astype(float).to_numpy())

    resumo = {
        "experimento": exp_id,
        "teste": tipo_teste,
        "amostras_treino": int(tab_tr["sample_id"].nunique()),
        "amostras_teste": int(tab_te["sample_id"].nunique()) if len(tab_te) else 0,
        "replicas_treino": int(len(tab_tr)), "replicas_teste": int(len(tab_te)),
        "combinacoes_avaliadas": int(len(placar)),
        "melhor": {k: (float(v) if isinstance(v, (np.floating, float)) else (int(v) if isinstance(v, (np.integer,)) else v))
                   for k, v in melhor.items()},
        "descricao_variante": DESCRICAO_VARIANTES.get(v_best, v_best),
        "formula_sisso": sisso_formula,
        "melhor_regressao": melhor_reg,
        "impressao_dados": _impressao_dados(ds_treino),
    }

    if registrar:
        pasta_m, cartao = salvar_pacote(
            final, feats, grade, cfg_best, float(melhor["limiar"]), f"{m_best} [{v_best}]",
            metricas_cv={"balanced_accuracy": melhor["cv_balanced_accuracy"], "roc_auc": melhor["cv_roc_auc"],
                         "sensibilidade": melhor["cv_sensibilidade"], "especificidade": melhor["cv_especificidade"]},
            info={"n_amostras": resumo["amostras_treino"], "n_linhas": resumo["replicas_treino"],
                  "impressao_dados": resumo["impressao_dados"]},
            pasta_modelos=pasta_modelos,
            extras={"experimento": exp_id, "variante": v_best,
                    "metricas_teste": {k.replace("teste_", ""): melhor[k] for k in melhor.index
                                       if k.startswith("teste_")},
                    "formula": formula, "regressor": melhor_reg["modelo"] if regressor_final is not None else None},
            adicionais={"regressor": regressor_final})
        resumo["modelo_registrado"] = cartao["id"]

    (pasta / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    from . import figuras
    figuras.gerar_todas(pasta, placar, prob_teste, (v_best, m_best), tabelas, reg, reg_pred, final, resumo)
    log.info("Experimento %s: melhor = %s/%s (CV BA %.3f; teste BA %s)", exp_id, v_best, m_best,
             melhor["cv_balanced_accuracy"], melhor.get("teste_balanced_accuracy"))
    return {"pasta": pasta, "placar": placar, "regressao": reg, "resumo": resumo, "modelo_final": final}


def ultimo_experimento(ds: Dataset, saida: str | Path = "resultados") -> dict | None:
    """Último experimento já rodado com exatamente estes dados (mesma impressão digital), ou None."""
    base = Path(saida)
    if not base.exists():
        return None
    alvo = _impressao_dados(ds)
    for pasta in sorted((p for p in base.iterdir() if (p / "resumo.json").exists()), reverse=True):
        resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
        if resumo.get("impressao_dados") == alvo:
            reg = pd.read_csv(pasta / "regressao.csv") if (pasta / "regressao.csv").exists() else pd.DataFrame()
            return {"pasta": pasta, "placar": pd.read_csv(pasta / "classificacao.csv"), "regressao": reg,
                    "resumo": resumo, "reaproveitado": True}
    return None
