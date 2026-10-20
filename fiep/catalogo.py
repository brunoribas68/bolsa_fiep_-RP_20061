"""Catálogo de modelos usados no treino e nos experimentos.

Cada entrada é um estimador do scikit-learn ainda não treinado. Os nomes aparecem nas tabelas
de resultados e no cartão do modelo.
"""
from __future__ import annotations

from sklearn.calibration import CalibratedClassifierCV
from sklearn.cross_decomposition import PLSRegression
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import (ExtraTreesClassifier, ExtraTreesRegressor, HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR

from .sisso import SissoClassificador

import sklearn

_SK = tuple(int(x) for x in sklearn.__version__.split(".")[:2])


def _l1(**kw):
    # o scikit-learn 1.8 trocou penalty="l1" por l1_ratio=1.0; aceita as duas versões
    pen = {"l1_ratio": 1.0} if _SK >= (1, 8) else {"penalty": "l1"}
    return LogisticRegression(solver="liblinear", **pen, **kw)


def _pipe(est, escalar=True):
    passos = [("imputar", SimpleImputer(strategy="median"))]
    if escalar:
        passos.append(("escalar", StandardScaler()))
    return Pipeline(passos + [("est", est)])


def classificadores(seed: int = 42, rapido: bool = False) -> dict:
    """Nome -> classificador. `rapido=True` devolve um subconjunto (testes e iterações)."""
    def svm(C):
        return _pipe(CalibratedClassifierCV(SVC(kernel="rbf", C=C, class_weight="balanced", random_state=seed),
                                            ensemble=False))
    todos = {
        "log_reg": _pipe(LogisticRegression(C=1.0, max_iter=5000, class_weight="balanced", random_state=seed)),
        "log_reg_C0.1": _pipe(LogisticRegression(C=0.1, max_iter=5000, class_weight="balanced", random_state=seed)),
        "log_reg_C0.01": _pipe(LogisticRegression(C=0.01, max_iter=5000, class_weight="balanced", random_state=seed)),
        "log_reg_l1": _pipe(_l1(C=0.5, max_iter=5000, class_weight="balanced", random_state=seed)),
        "lda": _pipe(LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
        "svm_rbf": svm(1.0),
        "svm_rbf_C10": svm(10.0),
        "knn": _pipe(KNeighborsClassifier(n_neighbors=7, weights="distance")),
        "random_forest": _pipe(RandomForestClassifier(n_estimators=500, class_weight="balanced",
                                                      random_state=seed, n_jobs=-1), escalar=False),
        "extra_trees": _pipe(ExtraTreesClassifier(n_estimators=500, class_weight="balanced",
                                                  random_state=seed, n_jobs=-1), escalar=False),
        "hist_gb": HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, class_weight="balanced",
                                                  random_state=seed),
        "sisso": SissoClassificador(n_sis=25, max_dim=2),
    }
    if rapido:
        return {k: todos[k] for k in ("log_reg", "random_forest", "sisso")}
    return todos


def regressores(seed: int = 42, rapido: bool = False) -> dict:
    todos = {
        "ridge": _pipe(RidgeCV(alphas=(0.01, 0.1, 1.0, 10.0, 100.0))),
        "pls": _pipe(PLSRegression(n_components=5)),
        "svr": _pipe(SVR(C=10.0)),
        "random_forest": _pipe(RandomForestRegressor(n_estimators=500, random_state=seed, n_jobs=-1), escalar=False),
        "extra_trees": _pipe(ExtraTreesRegressor(n_estimators=500, random_state=seed, n_jobs=-1), escalar=False),
        "hist_gb": HistGradientBoostingRegressor(learning_rate=0.05, max_iter=300, random_state=seed),
    }
    if rapido:
        return {k: todos[k] for k in ("ridge", "random_forest")}
    return todos
