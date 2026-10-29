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


# ----------------------------------------------------------------------------- nomes legíveis
# Fonte única dos nomes mostrados na plataforma, no `fiep modelos` e nos relatórios.
# nome: o que é; ajuste: o que distingue esta variação (hiperparâmetros); familia: grupo;
# o_que: como funciona, em uma ou duas frases; parametros: o que os números querem dizer.
INFO_CLASSIFICADORES = {
    "log_reg": dict(
        nome="Regressão logística", ajuste="regularização padrão, C = 1", familia="Linear",
        o_que="Modelo linear: uma soma ponderada das características vira a probabilidade de contaminação. "
              "Rápido, estável com poucas amostras e fácil de interpretar (os pesos mostram o que importa).",
        parametros="C é o inverso da força da regularização, que segura os pesos para o modelo não decorar o "
                   "treino. C = 1 é o padrão. Penalidade L2 (encolhe todos os pesos). Classes balanceadas: a "
                   "classe com menos amostras pesa mais."),
    "log_reg_C0.1": dict(
        nome="Regressão logística", ajuste="regularização forte, C = 0,1", familia="Linear",
        o_que="A mesma regressão logística, com os pesos mais contidos.",
        parametros="C = 0,1: regularização 10 vezes mais forte que o padrão (C = 1). Modelo mais simples, "
                   "menos sujeito a overfitting quando há muitas características (ex.: a curva inteira) e "
                   "poucas amostras."),
    "log_reg_C0.01": dict(
        nome="Regressão logística", ajuste="regularização muito forte, C = 0,01", familia="Linear",
        o_que="A mesma regressão logística, com os pesos bem contidos.",
        parametros="C = 0,01: regularização 100 vezes mais forte que o padrão. O modelo fica quase uma média "
                   "das características; serve para ver se um modelo bem simples já basta."),
    "log_reg_l1": dict(
        nome="Regressão logística esparsa", ajuste="L1, escolhe as características, C = 0,5", familia="Linear",
        o_que="Regressão logística que zera os pesos das características pouco úteis: o próprio modelo "
              "escolhe quais pontos da curva ou descritores usar.",
        parametros="Penalidade L1 (a que zera pesos) com C = 0,5, um pouco mais forte que o padrão."),
    "lda": dict(
        nome="Análise discriminante linear (LDA)", ajuste="com encolhimento automático", familia="Linear",
        o_que="Supõe que cada classe é uma nuvem com a mesma forma e traça a fronteira reta entre elas. "
              "Clássico em quimiometria.",
        parametros="Encolhimento (Ledoit-Wolf) estabiliza a estimativa das covariâncias quando há mais "
                   "características do que amostras."),
    "svm_rbf": dict(
        nome="SVM com núcleo RBF", ajuste="margem larga, C = 1", familia="Kernel",
        o_que="Máquina de vetores de suporte: procura a fronteira que deixa a maior margem entre as classes; "
              "o núcleo RBF permite fronteiras curvas. As probabilidades são calibradas.",
        parametros="C = 1: aceita alguns erros no treino em troca de uma margem mais larga (mais robusto)."),
    "svm_rbf_C10": dict(
        nome="SVM com núcleo RBF", ajuste="margem justa, C = 10", familia="Kernel",
        o_que="A mesma SVM, ajustando-se mais aos dados de treino.",
        parametros="C = 10: penaliza 10 vezes mais os erros no treino que o padrão; fronteira mais detalhada, "
                   "com mais risco de overfitting."),
    "knn": dict(
        nome="k vizinhos mais próximos", ajuste="7 vizinhos", familia="Vizinhança",
        o_que="Classifica pela maioria das amostras de treino mais parecidas, com peso maior para as mais "
              "próximas. Não aprende parâmetros; sofre com características irrelevantes.",
        parametros="k = 7 vizinhos, ponderados pela distância (características padronizadas)."),
    "random_forest": dict(
        nome="Floresta aleatória", ajuste="500 árvores", familia="Árvores",
        o_que="Média de muitas árvores de decisão, cada uma treinada com uma reamostragem dos dados e um "
              "sorteio de características. Captura relações não lineares; pouco sensível à configuração.",
        parametros="500 árvores, classes balanceadas, profundidade livre."),
    "extra_trees": dict(
        nome="Extra trees", ajuste="500 árvores, cortes sorteados", familia="Árvores",
        o_que="Como a floresta aleatória, mas os pontos de corte das árvores são sorteados; costuma variar "
              "menos de um conjunto de dados para outro.",
        parametros="500 árvores, classes balanceadas."),
    "hist_gb": dict(
        nome="Gradient boosting", ajuste="300 rodadas, taxa 0,05", familia="Árvores",
        o_que="Árvores pequenas treinadas em sequência, cada uma corrigindo os erros das anteriores (versão "
              "por histogramas, como o LightGBM). Muitas vezes o mais preciso em tabelas; pode sobreajustar "
              "com poucas amostras.",
        parametros="Até 300 rodadas com taxa de aprendizado 0,05 (passos pequenos), classes balanceadas."),
    "mlp": dict(
        nome="Rede neural (MLP)", ajuste="2 camadas: 64 e 32 neurônios", familia="Rede neural",
        o_que="Perceptron multicamadas: camadas de neurônios aprendem combinações não lineares das "
              "características.",
        parametros="Camadas ocultas de 64 e 32 neurônios, regularização alpha = 0,001 e parada antecipada "
                   "(para quando uma parte separada do treino deixa de melhorar)."),
    "mlp_aliev2024": dict(
        nome="Rede neural de Aliev et al. (2024)", ajuste="3 camadas de 250 neurônios", familia="Rede neural",
        o_que="Arquitetura do artigo de detecção de E. coli por voltametria cíclica (Biosensors and "
              "Bioelectronics 259:116377), treinada nos nossos dados: a rede original não foi publicada. "
              "Rede grande; precisa de muitas amostras.",
        parametros="3 camadas ocultas de 250 neurônios, taxa de aprendizado 0,001, parada antecipada, dados "
                   "normalizados entre 0 e 1 (MinMax), como no artigo."),
    "naive_bayes": dict(
        nome="Naive Bayes", ajuste="gaussiano", familia="Probabilístico",
        o_que="Supõe que cada característica é independente das outras e tem distribuição normal em cada "
              "classe. Muito simples; serve de referência mínima.",
        parametros="Sem hiperparâmetros a ajustar."),
    "sisso": dict(
        nome="SISSO (fórmula explícita)", ajuste="até 2 descritores", familia="Interpretável",
        o_que="Procura, entre combinações matemáticas dos descritores (somas, razões, logaritmos…), a "
              "fórmula de 1 ou 2 termos que melhor separa as classes. O resultado é uma equação que dá para "
              "escrever no artigo.",
        parametros="25 candidatos pré-selecionados por correlação (SIS) e fórmula com no máximo 2 termos."),
}

INFO_REGRESSORES = {
    "ridge": dict(nome="Regressão linear Ridge", ajuste="regularização escolhida por validação",
                  o_que="Reta (hiperplano) com os pesos contidos; a força da regularização é escolhida "
                        "automaticamente entre 0,01 e 100."),
    "pls": dict(nome="Mínimos quadrados parciais (PLS)", ajuste="5 componentes",
                o_que="Resume as características em 5 componentes ligados à carga e faz a regressão neles. "
                      "Clássico em quimiometria para curvas inteiras."),
    "svr": dict(nome="Regressão por vetores de suporte (SVR)", ajuste="núcleo RBF, C = 10",
                o_que="Versão de regressão da SVM; aceita relações não lineares."),
    "random_forest": dict(nome="Floresta aleatória", ajuste="500 árvores",
                          o_que="Média de 500 árvores de regressão."),
    "extra_trees": dict(nome="Extra trees", ajuste="500 árvores", o_que="Floresta com cortes sorteados."),
    "hist_gb": dict(nome="Gradient boosting", ajuste="300 rodadas, taxa 0,05",
                    o_que="Árvores em sequência, cada uma corrigindo as anteriores."),
    "mlp": dict(nome="Rede neural (MLP)", ajuste="64 e 32 neurônios", o_que="Perceptron multicamadas."),
    "mlp_aliev2024": dict(nome="Rede neural de Aliev et al. (2024)", ajuste="3 camadas de 250 neurônios",
                          o_que="Arquitetura do artigo de E. coli por voltametria cíclica."),
}


def nome_classificador(cid: str, curto: bool = False) -> str:
    """Nome legível ("Regressão logística — regularização forte, C = 0,1"). Desconhecido: o próprio id."""
    i = INFO_CLASSIFICADORES.get(cid)
    if not i:
        return cid
    return i["nome"] if curto else f"{i['nome']} — {i['ajuste']}"


def nome_regressor(rid: str) -> str:
    i = INFO_REGRESSORES.get(rid)
    return f"{i['nome']} — {i['ajuste']}" if i else rid


# Compatibilidade: (família, texto) e texto, como antes.
DESCRICAO_CLASSIFICADORES = {k: (v["familia"], f"{v['nome']} — {v['ajuste']}") for k, v in INFO_CLASSIFICADORES.items()}
DESCRICAO_REGRESSORES = {k: f"{v['nome']} — {v['ajuste']}" for k, v in INFO_REGRESSORES.items()}
