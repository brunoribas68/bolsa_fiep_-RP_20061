"""Ingestão: junta todas as fontes de dados num formato canônico único.

Fontes aceitas numa pasta de entrada (inclusive subpastas):

1. Tabelas (.csv/.xlsx) reconhecidas PELO CONJUNTO DE COLUNAS, como no case:
   - sinal       : measurement_id, potential_V, current_uA
   - metadados   : measurement_id, sample_id, contamination_status
   - plaqueamento: sample_id, colony_count
2. Arquivos .nox do NOVA + uma planilha de metadados com a coluna `arquivo`
   (nome do .nox). As demais colunas seguem o mesmo dicionário da planilha de
   metadados do case (sample_id, replicate_id, sensor_state, contamination_status...).
   Sem `measurement_id`, ele é gerado a partir do nome do arquivo.

Saída (formato canônico):
- medicoes : 1 linha por medição (identificação, rótulo, metadados)
- pontos   : 1 linha por ponto (measurement_id, scan_index, potential_v, current_ua,
             e_medido_v e i_bruta_ua — só para .nox, usados no controle de qualidade)
- amostras : 1 linha por amostra com a referência microbiológica (UFC) agregada
- relatorio: problemas encontrados na junção
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .io.nox import nox_to_curves

log = logging.getLogger(__name__)

EXT_TABELA = {".csv", ".txt", ".xlsx", ".xls"}

# a ordem importa: a planilha dos .nox também tem as colunas dos metadados, então vem antes
PAPEIS = {
    "indice_nox": {"arquivo", "sample_id"},
    "sinal": {"measurement_id", "potential_v", "current_ua"},
    "metadados": {"measurement_id", "sample_id", "contamination_status"},
    "plaqueamento": {"sample_id", "colony_count"},
}

COLS_MEDICAO = [
    "measurement_id", "sample_id", "replicate_id", "sensor_state", "tecnica", "fonte",
    "arquivo_origem", "contamination_status", "qc_flag", "target_bacterium", "sensor_id",
    "sensor_lot", "experimental_batch", "surface_type", "operator_id", "measurement_date",
    "sample_log10_mean_cfu_ml",
]


@dataclass
class Relatorio:
    arquivos: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)

    def aviso(self, msg: str) -> None:
        log.warning(msg)
        self.avisos.append(msg)

    def to_frame(self) -> pd.DataFrame:
        linhas = [{"tipo": "arquivo", "item": k, "detalhe": v} for k, v in self.arquivos.items()]
        linhas += [{"tipo": "aviso", "item": "", "detalhe": a} for a in self.avisos]
        return pd.DataFrame(linhas, columns=["tipo", "item", "detalhe"])


@dataclass
class Dataset:
    medicoes: pd.DataFrame
    pontos: pd.DataFrame
    amostras: pd.DataFrame
    relatorio: pd.DataFrame
    # plaqueamento bruto (1 linha por placa) e arquivos de origem (nome, papel, sha256),
    # usados pelo banco de dados para rastreabilidade
    plaqueamento: pd.DataFrame = field(default_factory=pd.DataFrame)
    arquivos: pd.DataFrame = field(default_factory=pd.DataFrame)

    def salvar(self, pasta: str | Path) -> None:
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        self.medicoes.to_csv(pasta / "medicoes.csv", index=False)
        self.pontos.to_csv(pasta / "pontos.csv.gz", index=False)
        self.amostras.to_csv(pasta / "amostras.csv", index=False)
        self.relatorio.to_csv(pasta / "relatorio_ingestao.csv", index=False)
        if len(self.plaqueamento):
            self.plaqueamento.to_csv(pasta / "plaqueamento.csv", index=False)
        if len(self.arquivos):
            self.arquivos.to_csv(pasta / "arquivos.csv", index=False)

    @classmethod
    def carregar(cls, pasta: str | Path) -> "Dataset":
        pasta = Path(pasta)
        return cls(
            medicoes=pd.read_csv(pasta / "medicoes.csv"),
            pontos=pd.read_csv(pasta / "pontos.csv.gz"),
            amostras=pd.read_csv(pasta / "amostras.csv"),
            relatorio=pd.read_csv(pasta / "relatorio_ingestao.csv"),
            plaqueamento=pd.read_csv(pasta / "plaqueamento.csv") if (pasta / "plaqueamento.csv").exists() else pd.DataFrame(),
            arquivos=pd.read_csv(pasta / "arquivos.csv") if (pasta / "arquivos.csv").exists() else pd.DataFrame(),
        )


def juntar(*conjuntos: "Dataset | None") -> "Dataset | None":
    """Une Datasets (ex.: dados soltos + pasta). Medições repetidas: fica a primeira."""
    cs = [d for d in conjuntos if d is not None and len(d.medicoes)]
    if not cs:
        return None
    if len(cs) == 1:
        return cs[0]

    def cat(attr, chave=None):
        df = _concat([getattr(d, attr) for d in cs if len(getattr(d, attr))])
        return df.drop_duplicates(chave) if chave and len(df) else df

    vistos: set = set()
    meds, ptss = [], []
    for d in cs:                                # cada medição vem inteira de um único conjunto
        novos = ~d.medicoes["measurement_id"].isin(vistos)
        meds.append(d.medicoes[novos])
        ptss.append(d.pontos[d.pontos["measurement_id"].isin(set(d.medicoes.loc[novos, "measurement_id"]))])
        vistos |= set(d.medicoes["measurement_id"])
    med, pts = _concat(meds), _concat(ptss)
    return Dataset(med.reset_index(drop=True), pts.reset_index(drop=True), cat("amostras", "sample_id"),
                   cat("relatorio"), cat("plaqueamento"), cat("arquivos"))


def sha256_arquivo(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _slug(s: str) -> str:
    return str(s).strip().lower().replace(" ", "_").replace("-", "_")


def _ler_tabela(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
        except UnicodeDecodeError:          # CSV salvo pelo Excel em português (Windows-1252)
            df = pd.read_csv(path, sep=None, engine="python", encoding="cp1252")
    df.columns = [_slug(c) for c in df.columns]
    return df


def classificar(df: pd.DataFrame) -> str | None:
    cols = set(df.columns)
    for papel, obrig in PAPEIS.items():
        if obrig <= cols:
            return papel
    return None


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _medicoes_do_case(sinal: pd.DataFrame, meta: pd.DataFrame, rel: Relatorio):
    sinal = sinal.copy()
    sinal["potential_v"] = pd.to_numeric(sinal["potential_v"], errors="coerce")
    sinal["current_ua"] = pd.to_numeric(sinal["current_ua"], errors="coerce")
    if "scan_index" not in sinal:
        sinal["scan_index"] = 1
    # no case, scan_index é a posição do ponto; todos os pontos pertencem a um único scan
    pontos = sinal[["measurement_id", "potential_v", "current_ua"]].copy()
    pontos["scan_index"] = 1
    pontos["e_medido_v"] = np.nan
    pontos["i_bruta_ua"] = np.nan

    dup = meta.duplicated("measurement_id").sum() if len(meta) else 0
    if dup:
        rel.aviso(f"{dup} measurement_id duplicados nos metadados (mantida a primeira ocorrência).")
        meta = meta.drop_duplicates("measurement_id")
    ids = pd.DataFrame({"measurement_id": sinal["measurement_id"].unique()})
    med = ids.merge(meta, on="measurement_id", how="left") if len(meta) else ids
    sem_meta = med["sample_id"].isna().sum() if "sample_id" in med else len(med)
    if sem_meta:
        rel.aviso(f"{sem_meta} medições de sinal sem metadados correspondentes.")
    med["fonte"] = "tabela"
    med["tecnica"] = med.get("tecnica", "DPV")
    med["arquivo_origem"] = sinal.groupby("measurement_id")["__arquivo"].first().reindex(med["measurement_id"]).values
    return med, pontos


def _medicoes_do_nox(arquivos: list[Path], indice: pd.DataFrame, rel: Relatorio, base: Path | None = None):
    if indice.empty:
        rel.aviso(f"{len(arquivos)} arquivo(s) .nox sem planilha de metadados (coluna 'arquivo'): "
                  "serão lidos, mas ficam sem rótulo nem amostra.")
        indice = pd.DataFrame({"arquivo": [a.name for a in arquivos]})
    indice = indice.copy().replace(r"^\s*$", np.nan, regex=True)
    indice = indice.dropna(subset=["arquivo"])
    indice["arquivo"] = indice["arquivo"].astype(str).str.strip().str.replace("\\", "/", regex=False)
    por_nome = {a.name: a for a in arquivos}
    por_nome.update({a.stem: a for a in arquivos})
    if base is not None:                     # caminho relativo (subpastas por empresa/data)
        por_nome.update({a.relative_to(base).as_posix(): a for a in arquivos})

    meds, pts = [], []
    for _, linha in indice.iterrows():
        caminho = (por_nome.get(linha["arquivo"]) or por_nome.get(Path(linha["arquivo"]).name)
                   or por_nome.get(Path(linha["arquivo"]).stem))
        if caminho is None:
            rel.aviso(f"Arquivo listado nos metadados não encontrado: {linha['arquivo']}")
            continue
        try:
            info, curvas = nox_to_curves(caminho)
        except Exception as e:  # noqa: BLE001 - registrar e seguir com o lote
            rel.aviso(f"Falha ao ler {caminho.name}: {e}")
            continue
        if not curvas:
            rel.aviso(f"{caminho.name}: nenhuma curva de potencial x corrente encontrada.")
            continue
        if len(curvas) > 1:
            rel.aviso(f"{caminho.name}: {len(curvas)} medições no mesmo arquivo; usando a primeira.")
        c = curvas[0]
        mid = linha.get("measurement_id")
        mid = mid if isinstance(mid, str) and mid else caminho.stem
        reg = {k: linha[k] for k in linha.index if k != "arquivo" and pd.notna(linha[k])}
        reg.update({"measurement_id": mid, "tecnica": c["tecnica"], "fonte": "nox",
                    "arquivo_origem": caminho.name})
        if info.get("leitura", "").startswith("PARCIAL"):
            rel.aviso(f"{caminho.name}: leitura parcial do arquivo.")
        meds.append(reg)
        n = len(c["potential_v"])
        pts.append(pd.DataFrame({
            "measurement_id": [mid] * n,
            "scan_index": c["scan_index"],
            "potential_v": c["potential_v"],
            "current_ua": c["current_ua"],
            "e_medido_v": c["e_medido_v"] if c["e_medido_v"] is not None else [np.nan] * n,
            "i_bruta_ua": c["i_bruta_ua"] if c["i_bruta_ua"] is not None else [np.nan] * n,
        }))
        rel.arquivos[caminho.name] = f"nox:{c['tecnica']} ({n} pontos)"
    usados = {m["arquivo_origem"] for m in meds}
    for a in arquivos:
        if a.name not in usados and a.name not in rel.arquivos:
            rel.aviso(f"{a.name}: .nox sem linha correspondente na planilha de metadados (ignorado).")
    return pd.DataFrame(meds), _concat(pts)


def _amostras(med: pd.DataFrame, plaq: pd.DataFrame, rel: Relatorio) -> pd.DataFrame:
    if "sample_id" not in med or med["sample_id"].isna().all():
        return pd.DataFrame(columns=["sample_id"])
    base = [c for c in ["sample_id", "target_bacterium", "contamination_status", "sensor_lot",
                        "sample_log10_mean_cfu_ml"] if c in med]
    am = med[base].dropna(subset=["sample_id"]).drop_duplicates("sample_id")
    if plaq.empty:
        return am
    col_cfu = "calculated_cfu_ml" if "calculated_cfu_ml" in plaq else "colony_count"
    agg = plaq.groupby("sample_id").agg(
        plaqueamento_ufc_ml_media=(col_cfu, "mean"),
        plaqueamento_log10_ufc_ml_media=("log10_cfu_ml", "mean") if "log10_cfu_ml" in plaq else (col_cfu, "mean"),
        plaqueamento_n_replicatas=("colony_count", "count"),
    ).reset_index()
    am = am.merge(agg, on="sample_id", how="left")
    falta = am["plaqueamento_n_replicatas"].isna().sum()
    if falta:
        rel.aviso(f"{falta} amostras sem plaqueamento de referência.")
    return am


def arquivos_de_dados(pasta: str | Path, excluir: tuple[str, ...] = ()) -> tuple[list[Path], list[Path]]:
    """(.nox, tabelas) da pasta e subpastas, ignorando as subpastas de primeiro nível em `excluir`."""
    pasta = Path(pasta)

    def ok(p: Path) -> bool:
        partes = p.relative_to(pasta).parts
        return p.is_file() and not (len(partes) > 1 and partes[0] in excluir)

    todos = [p for p in pasta.rglob("*") if ok(p)] if pasta.is_dir() else []
    return (sorted(p for p in todos if p.suffix.lower() == ".nox"),
            sorted(p for p in todos if p.suffix.lower() in EXT_TABELA))


def tem_dados(pasta: str | Path, excluir: tuple[str, ...] = ()) -> bool:
    noxs, tabelas = arquivos_de_dados(pasta, excluir)
    return bool(noxs or tabelas)


def ingerir(pasta_entrada: str | Path, excluir: tuple[str, ...] = ()) -> Dataset:
    """Lê tudo o que houver na pasta (exceto as subpastas em `excluir`) e devolve o Dataset canônico."""
    pasta = Path(pasta_entrada)
    rel = Relatorio()
    buckets: dict[str, list[pd.DataFrame]] = {p: [] for p in PAPEIS}
    noxs, tabelas = arquivos_de_dados(pasta, excluir)
    origem = []
    for arq in tabelas:
        try:
            df = _ler_tabela(arq)
        except Exception as e:  # noqa: BLE001
            rel.aviso(f"Não consegui ler {arq.name}: {e}")
            continue
        papel = classificar(df)
        if papel is None:
            rel.arquivos[arq.name] = "ignorado (colunas não reconhecidas)"
            continue
        df["__arquivo"] = arq.name
        buckets[papel].append(df)
        rel.arquivos[arq.name] = papel
        origem.append({"arquivo": arq.name, "papel": papel, "sha256": sha256_arquivo(arq),
                       "tamanho_bytes": arq.stat().st_size, "n_linhas": len(df)})

    sinal = _concat(buckets["sinal"])
    meta = _concat(buckets["metadados"])
    plaq = _concat(buckets["plaqueamento"])
    indice = _concat(buckets["indice_nox"])

    meds, pts = [], []
    if not sinal.empty:
        m, p = _medicoes_do_case(sinal, meta.drop(columns="__arquivo", errors="ignore"), rel)
        meds.append(m), pts.append(p)
    if noxs:
        m, p = _medicoes_do_nox(noxs, indice.drop(columns="__arquivo", errors="ignore"), rel, base=pasta)
        if len(m):
            meds.append(m), pts.append(p)
    if not meds:
        raise FileNotFoundError(f"Nenhum dado de sinal (.nox ou tabela de voltamogramas) em {pasta}")

    med = _concat(meds)
    for c in COLS_MEDICAO:
        if c not in med:
            med[c] = np.nan
    med = med[COLS_MEDICAO + [c for c in med.columns if c not in COLS_MEDICAO]]
    dup = med["measurement_id"].duplicated().sum()
    if dup:
        rel.aviso(f"{dup} measurement_id repetidos entre fontes (mantida a primeira ocorrência).")
        med = med.drop_duplicates("measurement_id")
    pontos = _concat(pts)
    pontos = pontos[pontos["measurement_id"].isin(med["measurement_id"])]
    amostras = _amostras(med, plaq, rel)
    usados_nox = set(med.loc[med["fonte"] == "nox", "arquivo_origem"])
    for a in noxs:
        if a.name in usados_nox:
            origem.append({"arquivo": a.name, "papel": "nox", "sha256": sha256_arquivo(a),
                           "tamanho_bytes": a.stat().st_size, "n_linhas": int((pontos["measurement_id"] ==
                           med.loc[med["arquivo_origem"] == a.name, "measurement_id"].iloc[0]).sum())})
    log.info("Ingestão: %d medições, %d pontos, %d amostras", len(med), len(pontos), len(amostras))
    return Dataset(med.reset_index(drop=True), pontos.reset_index(drop=True), amostras, rel.to_frame(),
                   plaqueamento=plaq.drop(columns="__arquivo", errors="ignore").assign(
                       arquivo_origem=plaq["__arquivo"]) if len(plaq) else pd.DataFrame(),
                   arquivos=pd.DataFrame(origem))
