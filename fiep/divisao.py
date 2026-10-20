"""Divisão dos dados em treino, validação e teste.

Regra (a mesma descrita em `dados/README.md` e no artigo):

* Dados colocados **direto em `dados/`** (ou em subpastas que não sejam as reservadas) formam um
  conjunto único que é dividido por **amostra**, estratificado pela classe, nas proporções de
  `[divisao]` da configuração — padrão 50% treino, 25% validação, 25% teste (Hastie, Tibshirani e
  Friedman, *The Elements of Statistical Learning*, 2.ª ed., seção 7.2).
* Dados nas pastas **`dados/treino/`, `dados/validacao/` e `dados/teste/`** vão inteiros para o
  conjunto correspondente e são **somados** à parte sorteada. Uma amostra que esteja numa pasta
  nunca é sorteada para outro conjunto.
* Se, no fim, a validação ou o teste ficarem vazios, eles são sorteados do treino nas mesmas
  proporções. Se não houver dado nenhum, usa `dados/exemplo_case/` (demonstração).

Papéis: o **treino** ajusta os modelos; a **validação** escolhe a combinação variante × modelo;
o **teste** é usado uma única vez, no modelo escolhido re-treinado com treino + validação.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from .ingest import Dataset, ingerir, juntar, tem_dados

log = logging.getLogger(__name__)

CONJUNTOS = ("treino", "validacao", "teste")
RESERVADAS = (*CONJUNTOS, "exemplo_case", "excel")     # dados/excel: cópias em Excel dos .nox
PROPORCOES_PADRAO = {"treino": 0.50, "validacao": 0.25, "teste": 0.25}
ROTULO = "contamination_status"


@dataclass
class Divisao:
    treino: Dataset
    validacao: Dataset | None
    teste: Dataset | None
    proporcoes: dict
    origem: dict = field(default_factory=dict)      # nº de amostras por conjunto e por origem

    def __getitem__(self, k):
        return getattr(self, k)

    def amostras(self, k) -> int:
        d = self[k]
        return int(d.medicoes["sample_id"].nunique()) if d is not None else 0

    def descricao(self) -> str:
        p = self.proporcoes
        partes = []
        for k in CONJUNTOS:
            o = self.origem.get(k, {})
            fontes = ", ".join(f"{n} {f}" for f, n in o.items() if n) or "0"
            partes.append(f"{k}: {self.amostras(k)} amostras ({fontes})")
        return (f"divisão {round(p['treino'] * 100)}/{round(p['validacao'] * 100)}/{round(p['teste'] * 100)} "
                f"por amostra, estratificada pela classe — " + "; ".join(partes))


def proporcoes(cfg: dict | None) -> dict:
    p = {**PROPORCOES_PADRAO, **((cfg or {}).get("divisao") or {})}
    p = {k: float(p[k]) for k in CONJUNTOS}
    tot = sum(p.values())
    if tot <= 0 or any(v < 0 for v in p.values()) or p["treino"] <= 0:
        raise ValueError(f"Proporções inválidas em [divisao]: {p}")
    return {k: v / tot for k, v in p.items()}


def _rotulos(ds: Dataset) -> pd.Series:
    """Classe de cada amostra (amostras sem rótulo ficam com -1)."""
    m = ds.medicoes.dropna(subset=["sample_id"])
    return m.groupby("sample_id")[ROTULO].max().fillna(-1).astype(int)


def _partir(ids: pd.Series, frac: float, seed: int):
    """Separa `frac` das amostras (estratificado quando possível). Devolve (resto, separadas)."""
    if frac <= 0 or len(ids) < 2:
        return list(ids.index), []
    n_sep = max(1, round(frac * len(ids)))
    if n_sep >= len(ids):
        return [], list(ids.index)
    estrat = ids.to_numpy() if ids.value_counts().min() >= 2 and n_sep >= ids.nunique() \
        and len(ids) - n_sep >= ids.nunique() else None
    resto, sep = train_test_split(list(ids.index), test_size=n_sep, random_state=seed, stratify=estrat)
    return resto, sep


def dividir(ds: Dataset, props: dict, seed: int = 42) -> dict[str, set]:
    """Sorteia as amostras de `ds` em treino/validação/teste nas proporções dadas."""
    ids = _rotulos(ds)
    resto, teste = _partir(ids, props["teste"], seed)
    frac_val = props["validacao"] / (props["treino"] + props["validacao"]) if props["validacao"] else 0
    treino, val = _partir(ids.loc[resto], frac_val, seed + 1)
    return {"treino": set(treino), "validacao": set(val), "teste": set(teste)}


def subconjunto(ds: Dataset, amostras) -> Dataset | None:
    amostras = set(amostras)
    if not amostras:
        return None
    med = ds.medicoes[ds.medicoes["sample_id"].isin(amostras)]
    ids = set(med["measurement_id"])
    return Dataset(med, ds.pontos[ds.pontos["measurement_id"].isin(ids)],
                   ds.amostras[ds.amostras["sample_id"].isin(amostras)] if len(ds.amostras) else ds.amostras,
                   ds.relatorio, ds.plaqueamento, ds.arquivos)


def _ids(ds: Dataset | None) -> set:
    return set(ds.medicoes["sample_id"].dropna()) if ds is not None else set()


def diagnosticar(ds: Dataset | None, cfg: dict | None = None) -> str:
    """Explica, em português, por que os dados lidos ainda não servem para treinar."""
    if ds is None or not len(ds.medicoes):
        return "Nenhuma medição foi lida (há .nox ou tabelas na pasta?)."
    m = ds.medicoes
    estagios = list((cfg or {}).get("dados", {}).get("estagios") or
                    ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"])
    tecnica = (cfg or {}).get("dados", {}).get("tecnica", "DPV")
    linhas = [f"Foram lidas {len(m)} medições de {m['arquivo_origem'].nunique()} arquivo(s)."]
    if "tecnica" in m and m["tecnica"].notna().any():
        tec = m["tecnica"].value_counts().to_dict()
        linhas.append(f"  Técnicas: {tec}." + ("" if tec.get(tecnica) else f" Nenhuma é {tecnica}, a usada no treino."))
    sem_id = m["sample_id"].isna()
    if sem_id.any():
        arqs = m.loc[sem_id, "arquivo_origem"].dropna().unique()
        linhas.append(f"  {sem_id.sum()} medições sem sample_id (ex.: {', '.join(map(str, arqs[:3]))}). "
                      "Coloque os .nox de cada amostra numa pasta própria ou corrija em metadados_nox.csv.")
    sem_rot = m["sample_id"].notna() & m["contamination_status"].isna()
    if sem_rot.any():
        ams = sorted(m.loc[sem_rot, "sample_id"].astype(str).unique())
        linhas.append(f"  {len(ams)} amostra(s) sem contamination_status (0 ou 1): {', '.join(ams[:5])}. "
                      "Informe o resultado do plaqueamento em amostras.csv (uma linha por amostra; "
                      "`fiep planilha --entrada <pasta do lote>` cria a tabela) ou use pastas "
                      "contaminada/ e nao_contaminada/.")
    rot = m.dropna(subset=["sample_id", "contamination_status"])
    if len(rot):
        classes = rot.groupby("sample_id")["contamination_status"].max().astype(int).value_counts().to_dict()
        linhas.append(f"  Amostras com rótulo: {classes} (1 = contaminada). São necessárias as duas classes.")
        if sum(classes.values()) < 20:
            linhas.append("  São poucas amostras para dividir em treino, validação e teste: junte mais lotes "
                          "(recomendado: dezenas de amostras de cada classe).")
        est = rot.groupby(["sample_id", "replicate_id"])["sensor_state"].apply(lambda s: set(s.dropna()))
        completas = int(sum(set(estagios) <= e for e in est))
        linhas.append(f"  Réplicas com os {len(estagios)} estágios ({', '.join(estagios)}): {completas} de {len(est)}.")
        if not completas:
            vistos = sorted(set().union(*est)) if len(est) else []
            linhas.append(f"  Estágios encontrados: {vistos or 'nenhum'}. O modelo usa a diferença entre estágios "
                          "do mesmo eletrodo, então cada réplica precisa dos três.")
    return "\n".join(linhas)


def montar(soltos: Dataset | None, fixos: dict[str, Dataset | None], cfg: dict | None = None) -> Divisao:
    """Junta os dados soltos (sorteados) com os das pastas (fixos) seguindo a regra do módulo."""
    props = proporcoes(cfg)
    seed = int((cfg or {}).get("modelo", {}).get("seed", 42))
    fixos = {k: fixos.get(k) for k in CONJUNTOS}
    origem = {k: {} for k in CONJUNTOS}

    # amostras com pasta definida não entram no sorteio (evita a mesma amostra em dois conjuntos)
    ja = set().union(*(_ids(d) for d in fixos.values()))
    repetidas = [s for k1 in CONJUNTOS for k2 in CONJUNTOS if k1 < k2 for s in _ids(fixos[k1]) & _ids(fixos[k2])]
    if repetidas:
        raise ValueError(f"Amostras em mais de uma pasta (treino/validacao/teste): {sorted(set(repetidas))[:10]}")

    brutos = juntar(soltos, *fixos.values())
    if brutos is not None and not _rotulos(brutos).ge(0).any():
        raise ValueError("Os dados ainda não têm amostras rotuladas para treinar.\n" + diagnosticar(brutos, cfg))

    sorteio = {k: None for k in CONJUNTOS}
    if soltos is not None:
        livres = _ids(soltos) - ja
        if len(livres) < len(_ids(soltos)):
            log.warning("%d amostras soltas já estão nas pastas e ficaram com a pasta.", len(_ids(soltos)) - len(livres))
        soltos = subconjunto(soltos, livres)
    if soltos is not None:
        partes = dividir(soltos, props, seed)
        sorteio = {k: subconjunto(soltos, partes[k]) for k in CONJUNTOS}

    final = {}
    for k in CONJUNTOS:
        final[k] = juntar(sorteio[k], fixos[k])
        origem[k] = {"sorteadas de dados/": len(_ids(sorteio[k])), f"da pasta {k}/": len(_ids(fixos[k]))}

    if final["treino"] is None:
        raise ValueError("Não há dados de treino (nem soltos em dados/ nem em dados/treino/).\n"
                         + diagnosticar(brutos, cfg))
    # validação ou teste vazios: sorteia do treino, nas mesmas proporções
    for k in ("teste", "validacao"):
        if final[k] is None and props[k] > 0:
            ids = _rotulos(final["treino"])
            frac = props[k] / sum(props[j] for j in CONJUNTOS if j == "treino" or final[j] is None)
            resto, sep = _partir(ids, frac, seed + (2 if k == "teste" else 3))
            if sep and resto:
                final[k] = subconjunto(final["treino"], sep)
                final["treino"] = subconjunto(final["treino"], resto)
                origem[k]["sorteadas do treino"] = len(sep)
                log.warning("Conjunto de %s vazio: %d amostras sorteadas do treino.", k, len(sep))
    d = Divisao(final["treino"], final["validacao"], final["teste"], props, origem)
    log.info(d.descricao())
    return d


def de_pastas(base: str | Path = "dados", cfg: dict | None = None) -> Divisao:
    """Monta a divisão a partir da pasta de dados (ver a regra no topo do módulo)."""
    base = Path(base)
    soltos = ingerir(base, excluir=RESERVADAS) if tem_dados(base, RESERVADAS) else None
    fixos = {k: ingerir(base / k) for k in CONJUNTOS if tem_dados(base / k)}
    if soltos is None and not fixos:
        exemplo = base / "exemplo_case"
        if not tem_dados(exemplo):
            raise FileNotFoundError(f"Nenhum dado em {base}/ (nem em {exemplo}/).")
        log.warning("Sem dados em %s: usando %s (demonstração).", base, exemplo)
        soltos = ingerir(exemplo)
    return montar(soltos, fixos, cfg)
