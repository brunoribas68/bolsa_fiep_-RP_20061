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
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import SVC, SVR

from .sisso import SissoClassificador

import sklearn

_SK = tuple(int(x) for x in sklearn.__version__.split(".")[:2])


def _l1(**kw):
    # o scikit-learn 1.8 trocou penalty="l1" por l1_ratio=1.0; aceita as duas versões
    pen = {"l1_ratio": 1.0} if _SK >= (1, 8) else {"penalty": "l1"}
    return LogisticRegression(solver="liblinear", **pen, **kw)


def _pipe(est, escalar=True, escalador=None):
    passos = [("imputar", SimpleImputer(strategy="median"))]
    if escalar:
        passos.append(("escalar", escalador if escalador is not None else StandardScaler()))
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
        "mlp": _pipe(MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3, max_iter=2000, early_stopping=True,
                                   random_state=seed)),
        # receita de Aliev et al. (2024), Biosens. Bioelectron. 259:116377 (E. coli por voltametria cíclica):
        # 3 camadas ocultas de 250 neurônios, taxa de aprendizado 1e-3, parada antecipada, MinMaxScaler.
        # A rede treinada deles não foi publicada; aqui é a mesma arquitetura treinada nos nossos dados.
        "mlp_aliev2024": _pipe(MLPClassifier(hidden_layer_sizes=(250, 250, 250), learning_rate_init=1e-3,
                                             max_iter=1000, early_stopping=True, random_state=seed),
                               escalador=MinMaxScaler()),
        "naive_bayes": _pipe(GaussianNB()),
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
        "mlp": _pipe(MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3, max_iter=3000, early_stopping=True,
                                  random_state=seed)),
        "mlp_aliev2024": _pipe(MLPRegressor(hidden_layer_sizes=(250, 250, 250), learning_rate_init=1e-3,
                                            max_iter=1000, early_stopping=True, random_state=seed),
                               escalador=MinMaxScaler()),
    }
    if rapido:
        return {k: todos[k] for k in ("ridge", "random_forest")}
    return todos


# Descrições para a plataforma e a documentação (nome -> (família, texto)).
DESCRICAO_CLASSIFICADORES = {
    "log_reg": ("Linear", "Regressão logística (L2, C=1)"),
    "log_reg_C0.1": ("Linear", "Regressão logística mais regularizada (C=0,1)"),
    "log_reg_C0.01": ("Linear", "Regressão logística muito regularizada (C=0,01)"),
    "log_reg_l1": ("Linear", "Regressão logística L1 (seleciona características)"),
    "lda": ("Linear", "Análise discriminante linear com encolhimento"),
    "svm_rbf": ("Kernel", "SVM com núcleo RBF (C=1), calibrada"),
    "svm_rbf_C10": ("Kernel", "SVM com núcleo RBF (C=10), calibrada"),
    "knn": ("Vizinhança", "k vizinhos mais próximos (k=7)"),
    "random_forest": ("Árvores", "Floresta aleatória (500 árvores)"),
    "extra_trees": ("Árvores", "Extra trees (500 árvores)"),
    "hist_gb": ("Árvores", "Gradient boosting por histogramas"),
    "mlp": ("Rede neural", "Perceptron multicamadas (64-32), parada antecipada"),
    "mlp_aliev2024": ("Rede neural", "Rede do artigo de Aliev et al. 2024 (E. coli, CV): 3 camadas de 250, MinMax, parada antecipada"),
    "naive_bayes": ("Probabilístico", "Naive Bayes gaussiano"),
    "sisso": ("Interpretável", "SISSO simplificado: fórmula explícita com 1-2 descritores"),
}
DESCRICAO_REGRESSORES = {
    "ridge": "Ridge (regularização escolhida por validação)",
    "pls": "Mínimos quadrados parciais (5 componentes)",
    "svr": "Regressão por vetores de suporte",
    "random_forest": "Floresta aleatória",
    "extra_trees": "Extra trees",
    "hist_gb": "Gradient boosting por histogramas",
    "mlp": "Rede neural (perceptron multicamadas)",
    "mlp_aliev2024": "Rede neural de Aliev et al. 2024 (3 camadas de 250)",
}
