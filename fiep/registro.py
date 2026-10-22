"""Modelos registrados: lista, detalhes (métricas, comparação, figuras) e troca do modelo em uso.

Cada `fiep experimento` grava o melhor modelo em `modelos/<id>/` (cartao.json + modelo.joblib) e os
resultados completos em `resultados/<experimento>/` (comparação de todas as combinações, regressão,
figuras). `modelos/ATUAL` diz qual está em uso pela plataforma e pelo `fiep prever`.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

FIGURAS = {
    "comparacao_modelos.png": "Acurácia balanceada de cada representação × modelo (validação)",
    "roc_teste.png": "Curvas ROC no teste",
    "matriz_confusao_teste.png": "Matriz de confusão no teste",
    "curvas_diferenca.png": "Curva de diferença entre etapas, por classe",
    "importancia.png": "Importância das características (permutação, teste)",
    "regressao_teste.png": "Carga prevista × plaqueamento (teste)",
}


def _num(v):
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _limpo(obj):
    if isinstance(obj, dict):
        return {k: _limpo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_limpo(v) for v in obj]
    return _num(obj)


def atual(pasta_modelos: str | Path = "modelos") -> str | None:
    f = Path(pasta_modelos) / "ATUAL"
    return f.read_text().strip() if f.exists() else None


def _acuracia(m: dict | None) -> float | None:
    if not m:
        return None
    try:
        vp, fp, vn, fn = (float(m[k]) for k in ("vp", "fp", "vn", "fn"))
        return (vp + vn) / (vp + fp + vn + fn) if vp + fp + vn + fn else None
    except (KeyError, TypeError, ValueError):
        return None


def resumo_cartao(c: dict, em_uso: str | None) -> dict:
    teste = c.get("metricas_teste") or {}
    return _limpo({
        "id": c["id"], "criado_em": c.get("criado_em"), "modelo": c.get("modelo"), "variante": c.get("variante"),
        "protocolo": c.get("protocolo"), "experimento": c.get("experimento"), "n_amostras": c.get("n_amostras"),
        "limiar": c.get("limiar"), "em_uso": c["id"] == em_uso, "commit": c.get("commit"),
        "teste_acuracia": _acuracia(teste), "teste_balanced_accuracy": teste.get("balanced_accuracy"),
        "teste_sensibilidade": teste.get("sensibilidade"), "teste_especificidade": teste.get("especificidade"),
        "teste_roc_auc": teste.get("roc_auc"),
        "teste_amostra_balanced_accuracy": (c.get("teste_por_amostra") or {}).get("balanced_accuracy"),
        "validacao_balanced_accuracy": (c.get("metricas_validacao") or {}).get("balanced_accuracy"),
        "cv_balanced_accuracy": (c.get("metricas_cv") or {}).get("balanced_accuracy"),
        "regressor": c.get("regressor"),
    })


def listar(pasta_modelos: str | Path = "modelos") -> list[dict]:
    base = Path(pasta_modelos)
    em_uso = atual(base)
    cartoes = []
    for f in sorted(base.glob("*/cartao.json"), reverse=True):
        try:
            cartoes.append(resumo_cartao(json.loads(f.read_text(encoding="utf-8")), em_uso))
        except (json.JSONDecodeError, KeyError):
            continue
    return cartoes


def pasta_experimento(cartao: dict, pasta_resultados: str | Path = "resultados") -> Path | None:
    for p in (cartao.get("pasta_experimento"), Path(pasta_resultados) / str(cartao.get("experimento"))):
        if p and Path(p).is_dir():
            return Path(p)
    return None


def _csv(arq: Path) -> list[dict]:
    if not arq.exists():
        return []
    df = pd.read_csv(arq)
    return _limpo(json.loads(df.to_json(orient="records")))


def detalhe(id_: str, pasta_modelos: str | Path = "modelos", pasta_resultados: str | Path = "resultados") -> dict:
    arq = Path(pasta_modelos) / id_ / "cartao.json"
    if not arq.exists():
        raise FileNotFoundError(f"Modelo {id_} não encontrado em {pasta_modelos}/")
    c = json.loads(arq.read_text(encoding="utf-8"))
    pasta = pasta_experimento(c, pasta_resultados)
    resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8")) if pasta and (pasta / "resumo.json").exists() else {}
    base = resumo_cartao(c, atual(pasta_modelos))
    if base.get("teste_amostra_balanced_accuracy") is None:
        base["teste_amostra_balanced_accuracy"] = (resumo.get("teste_por_amostra") or {}).get("balanced_accuracy")
    base["protocolo"] = base.get("protocolo") or resumo.get("protocolo")
    return _limpo({
        **base,
        "cartao": c,
        "resumo": resumo,
        "comparacao": _csv(pasta / "classificacao.csv") if pasta else [],
        "regressao": _csv(pasta / "regressao.csv") if pasta else [],
        "teste_por_amostra": _csv(pasta / "teste_por_amostra.csv") if pasta else [],
        "figuras": [{"arquivo": f, "titulo": t} for f, t in FIGURAS.items() if pasta and (pasta / "figuras" / f).exists()],
    })


def figura(id_: str, nome: str, pasta_modelos: str | Path = "modelos", pasta_resultados: str | Path = "resultados") -> Path:
    if nome not in FIGURAS:
        raise FileNotFoundError(nome)
    c = json.loads((Path(pasta_modelos) / id_ / "cartao.json").read_text(encoding="utf-8"))
    pasta = pasta_experimento(c, pasta_resultados)
    arq = pasta / "figuras" / nome if pasta else None
    if arq is None or not arq.exists():
        raise FileNotFoundError(nome)
    return arq


def ativar(id_: str, pasta_modelos: str | Path = "modelos") -> None:
    base = Path(pasta_modelos)
    if not (base / id_ / "modelo.joblib").exists():
        raise FileNotFoundError(f"Modelo {id_} não encontrado em {base}/")
    (base / "ATUAL").write_text(id_)
