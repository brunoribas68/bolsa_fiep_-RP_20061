"""SISSO simplificado para classificação: um descritor explícito de poucas variáveis.

Inspirado em Ouyang et al. (2018), "SISSO: a compressed-sensing method for identifying the best
low-dimensional descriptor in an immensity of offered candidates", Phys. Rev. Materials 2, 083802.

Diferenças em relação ao SISSO original (deixe isso claro ao citar):
- o espaço de candidatos é gerado com UMA aplicação dos operadores (x, x², √|x|, log|x|,
  xi−xj, xi·xj, xi/xj) sobre os descritores primários padronizados, e não de forma recursiva;
- a triagem (SIS) usa a separação entre as classes de cada candidato isolado (AUC);
- o operador de esparsidade (SO) é uma busca exaustiva das combinações de 1..`max_dim`
  candidatos, escolhendo a de maior acurácia balanceada de uma regressão logística no treino
  (o original minimiza a sobreposição dos domínios das classes).

O resultado é uma fórmula legível, ex.: `p = σ(1.8·(Δi_pico/área_probe) − 0.4·e_pico + 0.2)`.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

_EPS = 1e-9


class SissoClassificador(ClassifierMixin, BaseEstimator):
    """Parâmetros
    ----------
    n_sis : nº de candidatos mantidos na triagem.
    max_dim : nº máximo de candidatos combinados no descritor final.
    excluir_prefixos : colunas ignoradas como descritores primários (ex.: pontos da curva).
    max_primarios : limita os primários aos de maior AUC isolada (controla o tamanho do espaço).
    """

    def __init__(self, n_sis=25, max_dim=2, excluir_prefixos=("D_", "I_"), max_primarios=30, C=10.0):
        self.n_sis = n_sis
        self.max_dim = max_dim
        self.excluir_prefixos = excluir_prefixos
        self.max_primarios = max_primarios
        self.C = C

    # ----- espaço de candidatos -------------------------------------------------------
    def _primarios(self, X: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in X.columns if not str(c).startswith(tuple(self.excluir_prefixos))]
        return X[cols].astype(float)

    @staticmethod
    def _sep(f: np.ndarray, y: np.ndarray) -> float:
        ok = np.isfinite(f)
        if ok.sum() < 5 or len(set(y[ok])) < 2 or np.nanstd(f[ok]) < _EPS:
            return 0.0
        auc = roc_auc_score(y[ok], f[ok])
        return abs(auc - 0.5)

    def _expandir(self, Z: pd.DataFrame) -> dict:
        cand = {}
        nomes = list(Z.columns)
        for a in nomes:
            x = Z[a].to_numpy()
            cand[a] = x
            cand[f"({a})^2"] = x ** 2
            cand[f"sqrt|{a}|"] = np.sqrt(np.abs(x))
            cand[f"log|{a}|"] = np.log(np.abs(x) + 1e-3)
        for a, b in combinations(nomes, 2):
            xa, xb = Z[a].to_numpy(), Z[b].to_numpy()
            cand[f"({a}-{b})"] = xa - xb
            cand[f"({a}*{b})"] = xa * xb
            with np.errstate(divide="ignore", invalid="ignore"):
                r = np.where(np.abs(xb) > 0.05, xa / xb, np.nan)
            cand[f"({a}/{b})"] = r
        return cand

    def fit(self, X, y):
        X = pd.DataFrame(X).copy()
        y = np.asarray(y).astype(int)
        P = self._primarios(X)
        self.mediana_ = P.median()
        P = P.fillna(self.mediana_)
        self.media_, self.desvio_ = P.mean(), P.std().replace(0, 1.0)
        Z = (P - self.media_) / self.desvio_
        # limita os primários aos mais informativos isoladamente
        sep = {c: self._sep(Z[c].to_numpy(), y) for c in Z.columns}
        self.primarios_ = sorted(sep, key=sep.get, reverse=True)[: self.max_primarios]
        cand = self._expandir(Z[self.primarios_])
        score = {k: self._sep(v, y) for k, v in cand.items()}
        self.sis_ = sorted(score, key=score.get, reverse=True)[: self.n_sis]
        F = pd.DataFrame({k: cand[k] for k in self.sis_})
        self.f_mediana_ = F.median()
        F = F.fillna(self.f_mediana_)
        self.f_media_, self.f_desvio_ = F.mean(), F.std().replace(0, 1.0)
        Fz = (F - self.f_media_) / self.f_desvio_

        melhor = (-1.0, -1.0, None, None)
        for d in range(1, self.max_dim + 1):
            for combo in combinations(self.sis_, d):
                lr = LogisticRegression(C=self.C, class_weight="balanced", max_iter=2000)
                lr.fit(Fz[list(combo)], y)
                p = lr.predict_proba(Fz[list(combo)])[:, 1]
                ba = balanced_accuracy_score(y, (p >= 0.5).astype(int))
                auc = roc_auc_score(y, p)
                if (ba, auc) > melhor[:2]:
                    melhor = (ba, auc, combo, lr)
        _, _, self.descritor_, self.lr_ = melhor
        self.classes_ = np.array([0, 1])
        return self

    def _descritores(self, X) -> pd.DataFrame:
        X = pd.DataFrame(X)
        P = self._primarios(X).reindex(columns=self.media_.index).fillna(self.mediana_)
        Z = (P - self.media_) / self.desvio_
        cand = self._expandir(Z[self.primarios_])
        F = pd.DataFrame({k: cand[k] for k in self.descritor_}).fillna(self.f_mediana_[list(self.descritor_)])
        return (F - self.f_media_[list(self.descritor_)]) / self.f_desvio_[list(self.descritor_)]

    def predict_proba(self, X):
        p = self.lr_.predict_proba(self._descritores(X))[:, 1]
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

    def formula(self) -> str:
        termos = [f"{w:+.3f}·[{n}]" for w, n in zip(self.lr_.coef_[0], self.descritor_)]
        return f"p(contaminada) = σ({' '.join(termos)} {self.lr_.intercept_[0]:+.3f})  (termos padronizados)"
