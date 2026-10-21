"""Preenchimento automático dos metadados de um lote de .nox.

Ninguém deve preencher arquivo por arquivo. O que dá para saber sem a pessoa é deduzido do
próprio .nox e da organização das pastas; a planilha `metadados_nox.csv` só serve para conferir
e corrigir (um valor preenchido nela sempre vence o deduzido).

| Campo | De onde vem |
|---|---|
| `sensor_state` | nome do arquivo e, se ele não disser, nome do procedimento gravado no .nox (palavras-chave de cada protocolo, `fiep/protocolos.py`) |
| `replicate_id` | eletrodo no nome (`bloqueio-E3` -> `E3`); senão, canal do potenciostato (`MAC80058#2` -> `2`) ou o sufixo do nome |
| `sample_id` | a pasta do arquivo: uma pasta = uma amostra. Se a mesma pasta tiver dois arquivos do mesmo estágio no mesmo canal, separa por dia da medição |
| `contamination_status` | nome de pasta/arquivo (`contaminada`, `nao_contaminada`, `positivo`, `negativo`, `controle_neg`) ou a tabela de amostras (`amostras.csv`, uma linha por amostra) |
| `measurement_date` | data gravada no .nox |
| tudo | `[metadados].padrao_nome`: expressão regular com grupos nomeados, para quem tem um padrão de nome de arquivo |

O rótulo (contaminada ou não) não sai do voltamograma — é o que o modelo prevê. Ele vem do
plaqueamento, informado uma vez por AMOSTRA em `amostras.csv` (ou pelo nome da pasta).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROTULO_PALAVRAS = [     # negativo antes do positivo: "nao_contaminada" contém "contaminada"
    (r"n[aã]o[_\- ]?contaminad|negativ|control[e]?[_\- ]?neg|\bneg\b|esteril|limpa\b", 0),
    (r"contaminad|positiv|control[e]?[_\- ]?pos|\bpos\b", 1),
]
BACTERIAS = [(r"e[_\-. ]?coli", "E. coli"), (r"salmonel", "Salmonella"), (r"listeri", "Listeria"),
             (r"staph|aureus", "S. aureus"), (r"pseudomon", "Pseudomonas")]


def _busca(regras, texto):
    for rx, valor in regras:
        if re.search(rx, texto, re.I):
            return valor
    return None


def estagio(texto: str, cfg: dict | None = None) -> str | None:
    from .protocolos import estagio as _est
    return _est(texto, cfg)


def _eletrodo(stem: str) -> str | None:
    """Eletrodo indicado no nome: bloqueio-E1, DPV_limpo_E2, eletrodo_3 -> E1, E2, E3."""
    m = re.search(r"(?:^|[_\-\s.])(?:e|el|eletrodo|electrode)[_\-\s]?(\d{1,3})(?=$|[_\-\s.])", stem, re.I)
    return f"E{int(m.group(1))}" if m else None


def _canal(instrumento) -> str | None:
    m = re.search(r"#\s*([A-Za-z0-9]+)\s*$", str(instrumento or ""))
    return m.group(1) if m else None


def _sufixo(stem: str) -> str | None:
    m = re.search(r"[_\-\s]([A-Za-z]?\d{1,3}|[A-Za-z])$", stem)
    return m.group(1) if m else None


def _slug(s: str) -> str:
    return re.sub(r"[^\w\-]+", "_", s).strip("_") or "amostra"


def id_medicao(sample_id, stem: str) -> str:
    """measurement_id estável: o mesmo arquivo recebe o mesmo id, seja qual for a pasta importada."""
    if sample_id is None or (isinstance(sample_id, float) and pd.isna(sample_id)) or str(sample_id) in stem:
        return stem
    return f"{sample_id}__{stem}"


def inferir(arquivos: list[Path], infos: dict[Path, dict] | None = None, cfg: dict | None = None) -> pd.DataFrame:
    """Uma linha por .nox com os metadados deduzidos e a coluna `preenchido_auto` (campos deduzidos).

    `infos` são os cabeçalhos já lidos dos .nox (para não ler duas vezes); os que faltarem são lidos.
    """
    from .io.nox import read_nox
    padrao = ((cfg or {}).get("metadados") or {}).get("padrao_nome") or ""
    rx = re.compile(padrao, re.I) if padrao else None
    linhas = []
    for arq in arquivos:
        info = (infos or {}).get(arq)
        if info is None:
            try:
                info = read_nox(arq)["info"]
            except Exception:  # noqa: BLE001
                info = {}
        proc = str(info.get("procedimento") or "")
        caminho = arq.as_posix()
        auto = {}
        if rx and (m := rx.search(caminho)):
            auto.update({k: v for k, v in m.groupdict().items() if v})
        # nome do arquivo primeiro (é o que a pessoa escolhe a cada medição); depois o procedimento
        if "sensor_state" not in auto and (e := estagio(arq.stem, cfg) or estagio(proc, cfg)):
            auto["sensor_state"] = e
        # eletrodo: pelo nome (E1, E2...) e, se não houver, pelo canal do potenciostato
        if "replicate_id" not in auto and (r := _eletrodo(arq.stem) or _canal(info.get("instrumento"))
                                           or _sufixo(arq.stem)):
            auto["replicate_id"] = r
        if "contamination_status" not in auto:
            r = _busca(ROTULO_PALAVRAS, " ".join(arq.parent.parts[-3:]) + " " + arq.stem)
            if r is not None:
                auto["contamination_status"] = r
        if "target_bacterium" not in auto and (b := _busca(BACTERIAS, f"{caminho} {proc}")):
            auto["target_bacterium"] = b
        data = str(info.get("data_hora_procedimento") or "")[:10]
        if data and data != "None":
            auto["measurement_date"] = data
        linhas.append({"_caminho": arq, "_pasta": arq.parent, "_dia": data.replace("-", ""), **auto})
    df = pd.DataFrame(linhas)
    if df.empty:
        return df

    # amostra = pasta; se a pasta repete (estágio, canal), separa pelo dia da medição
    if "sample_id" not in df:
        df["sample_id"] = None
    sem = df["sample_id"].isna()
    # pastas de amostra com o mesmo nome em lugares diferentes (ex.: contaminada/A01 e nao_contaminada/A01)
    nomes = pd.Series({p: Path(p).name for p in df.loc[sem, "_pasta"].unique()})
    repetidos = set(nomes[nomes.duplicated(keep=False)])
    for pasta, g in df[sem].groupby("_pasta"):
        cols = g.reindex(columns=["sensor_state", "replicate_id"])
        chave = cols.iloc[:, 0].map(str) + "|" + cols.iloc[:, 1].map(str)
        base = _slug(Path(pasta).name if Path(pasta).name not in repetidos
                     else f"{Path(pasta).parent.name}_{Path(pasta).name}")
        if chave.duplicated().any():
            df.loc[g.index, "sample_id"] = base + "_" + g["_dia"].replace("", "semdata")
        else:
            df.loc[g.index, "sample_id"] = base
        df.loc[g.index, "_amostra_auto"] = True
    campos = ["sample_id", "replicate_id", "sensor_state", "contamination_status", "target_bacterium",
              "measurement_date"]
    df["measurement_id"] = [id_medicao(s, p.stem) for s, p in zip(df["sample_id"], df["_caminho"])]
    df["preenchido_auto"] = [", ".join(c for c in campos if c in df and pd.notna(r.get(c))) for _, r in df.iterrows()]
    return df


def tabela_amostras(auto: pd.DataFrame, estagios: list[str]) -> pd.DataFrame:
    """Uma linha por amostra deduzida: é a tabela pequena que a equipe completa (rótulo e carga)."""
    if auto.empty:
        return pd.DataFrame()
    g = auto.groupby("sample_id")
    out = pd.DataFrame({
        "sample_id": list(g.groups),
        "contamination_status": [g.get_group(s).get("contamination_status", pd.Series(dtype=object)).dropna()
                                 .astype(int).max() if "contamination_status" in auto else None for s in g.groups],
        "sample_log10_mean_cfu_ml": None,
        "target_bacterium": [g.get_group(s).get("target_bacterium", pd.Series(dtype=object)).dropna()
                             .head(1).squeeze() if "target_bacterium" in auto else None for s in g.groups],
        "surface_type": None,
        "n_arquivos": g.size().to_list(),
        "n_replicas": g["replicate_id"].nunique().to_list() if "replicate_id" in auto else None,
        "estagios_encontrados": [", ".join(e for e in estagios if e in set(g.get_group(s).get("sensor_state", [])))
                                 for s in g.groups],
    })
    out["contamination_status"] = out["contamination_status"].apply(
        lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) or isinstance(v, pd.Series) else int(v))
    out["target_bacterium"] = out["target_bacterium"].apply(lambda v: "" if isinstance(v, pd.Series) or v is None else v)
    faltam = [", ".join(e for e in estagios if e not in s.split(", ")) for s in out["estagios_encontrados"]]
    out["observacoes"] = ["faltam estágios: " + f if f else "" for f in faltam]
    return out
