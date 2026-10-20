"""Banco de dados do projeto (SQLite).

Um único arquivo (padrão: `dados/fiep.db`) com tudo rastreável:

    arquivos      cada arquivo importado (nome, papel, sha256) — reimportar o mesmo arquivo não duplica
    importacoes   cada execução de importação (quando, de onde, quanto entrou)
    amostras      1 linha por amostra (bactéria, rótulo, carga de referência)
    plaqueamentos 1 linha por placa (referência microbiológica bruta)
    medicoes      1 linha por voltamograma (amostra, réplica, estágio do sensor, técnica, lote...)
    pontos        1 linha por ponto do voltamograma
    qc            resultado do controle de qualidade por medição (histórico por versão da pipeline)
    modelos       cada modelo treinado (métricas, limiar, commit, impressão digital dos dados)
    predicoes     cada previsão feita, ligada ao modelo que a gerou

Views prontas para consulta: v_medicoes, v_replicatas, v_qc_atual, v_predicoes.

Abra o arquivo no DB Browser for SQLite ou no DBeaver, ou exporte com `fiep db exportar`.
O esquema usa SQL padrão para facilitar uma migração futura para Postgres.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .ingest import Dataset

VERSAO_ESQUEMA = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta_esquema (
    versao INTEGER NOT NULL,
    atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    importado_em TEXT NOT NULL,
    origem TEXT,
    versao_pipeline TEXT,
    n_medicoes INTEGER,
    n_pontos INTEGER,
    n_amostras INTEGER,
    avisos TEXT
);

CREATE TABLE IF NOT EXISTS arquivos (
    sha256 TEXT PRIMARY KEY,
    arquivo TEXT NOT NULL,
    papel TEXT NOT NULL,
    tamanho_bytes INTEGER,
    n_linhas INTEGER,
    importacao_id INTEGER REFERENCES importacoes(id),
    importado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS amostras (
    sample_id TEXT PRIMARY KEY,
    target_bacterium TEXT,
    contamination_status INTEGER CHECK (contamination_status IN (0, 1)),
    sample_log10_mean_cfu_ml REAL,
    sensor_lot TEXT,
    extras TEXT,
    atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plaqueamentos (
    sample_id TEXT NOT NULL REFERENCES amostras(sample_id),
    plating_replicate_id INTEGER NOT NULL,
    colony_count REAL,
    dilution_exponent REAL,
    plated_volume_ml REAL,
    plating_qualifier TEXT,
    calculated_cfu_ml REAL,
    log10_cfu_ml REAL,
    arquivo_origem TEXT,
    extras TEXT,
    PRIMARY KEY (sample_id, plating_replicate_id)
);

CREATE TABLE IF NOT EXISTS medicoes (
    measurement_id TEXT PRIMARY KEY,
    sample_id TEXT REFERENCES amostras(sample_id),
    replicate_id INTEGER,
    sensor_state TEXT,
    tecnica TEXT,
    fonte TEXT,
    arquivo_origem TEXT,
    contamination_status INTEGER CHECK (contamination_status IN (0, 1)),
    qc_flag TEXT,
    target_bacterium TEXT,
    sensor_id TEXT,
    sensor_lot TEXT,
    experimental_batch TEXT,
    surface_type TEXT,
    operator_id TEXT,
    measurement_date TEXT,
    sample_log10_mean_cfu_ml REAL,
    extras TEXT,
    importacao_id INTEGER REFERENCES importacoes(id)
);
CREATE INDEX IF NOT EXISTS ix_medicoes_amostra ON medicoes(sample_id, replicate_id);

CREATE TABLE IF NOT EXISTS pontos (
    measurement_id TEXT NOT NULL REFERENCES medicoes(measurement_id) ON DELETE CASCADE,
    scan_index INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    potential_v REAL,
    current_ua REAL,
    e_medido_v REAL,
    i_bruta_ua REAL,
    PRIMARY KEY (measurement_id, scan_index, idx)
);

CREATE TABLE IF NOT EXISTS qc (
    measurement_id TEXT NOT NULL REFERENCES medicoes(measurement_id) ON DELETE CASCADE,
    versao_pipeline TEXT NOT NULL,
    avaliado_em TEXT NOT NULL,
    qc_auto TEXT,
    qc_planilha TEXT,
    qc_final TEXT,
    qc_motivos TEXT,
    i_max_ua REAL,
    PRIMARY KEY (measurement_id, versao_pipeline)
);

CREATE TABLE IF NOT EXISTS modelos (
    id TEXT PRIMARY KEY,
    criado_em TEXT NOT NULL,
    algoritmo TEXT,
    versao_pipeline TEXT,
    commit_codigo TEXT,
    limiar REAL,
    balanced_accuracy REAL,
    sensibilidade REAL,
    especificidade REAL,
    roc_auc REAL,
    n_amostras INTEGER,
    impressao_dados TEXT,
    caminho TEXT,
    cartao TEXT
);

CREATE TABLE IF NOT EXISTS predicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modelo_id TEXT NOT NULL REFERENCES modelos(id),
    previsto_em TEXT NOT NULL,
    sample_id TEXT,
    replicate_id INTEGER,
    measurement_id TEXT,
    status TEXT,
    resultado TEXT,
    prob_contaminada REAL,
    confianca REAL,
    motivo TEXT,
    rotulo_informado INTEGER
);

CREATE VIEW IF NOT EXISTS v_qc_atual AS
    SELECT q.* FROM qc q
    WHERE q.avaliado_em = (SELECT MAX(q2.avaliado_em) FROM qc q2 WHERE q2.measurement_id = q.measurement_id);

CREATE VIEW IF NOT EXISTS v_medicoes AS
    SELECT m.measurement_id, m.sample_id, m.replicate_id, m.sensor_state, m.tecnica, m.fonte,
           m.arquivo_origem, COALESCE(m.contamination_status, a.contamination_status) AS contamination_status,
           a.target_bacterium, m.sensor_lot, m.experimental_batch, m.surface_type, m.measurement_date,
           m.qc_flag AS qc_planilha, q.qc_auto, q.qc_final, q.qc_motivos,
           (SELECT COUNT(*) FROM pontos p WHERE p.measurement_id = m.measurement_id) AS n_pontos
    FROM medicoes m
    LEFT JOIN amostras a ON a.sample_id = m.sample_id
    LEFT JOIN v_qc_atual q ON q.measurement_id = m.measurement_id;

CREATE VIEW IF NOT EXISTS v_replicatas AS
    SELECT sample_id, replicate_id,
           COUNT(*) AS n_medicoes,
           GROUP_CONCAT(sensor_state, ', ') AS estagios,
           SUM(CASE WHEN qc_final = 'PASS' OR (qc_final IS NULL AND COALESCE(qc_planilha, 'PASS') = 'PASS')
                    THEN 1 ELSE 0 END) AS n_aprovadas,
           MAX(contamination_status) AS contamination_status
    FROM v_medicoes
    GROUP BY sample_id, replicate_id;

CREATE VIEW IF NOT EXISTS v_predicoes AS
    SELECT p.*, m.algoritmo, m.balanced_accuracy AS modelo_balanced_accuracy
    FROM predicoes p JOIN modelos m ON m.id = p.modelo_id;
"""

COLS = {
    "amostras": ["sample_id", "target_bacterium", "contamination_status", "sample_log10_mean_cfu_ml", "sensor_lot"],
    "plaqueamentos": ["sample_id", "plating_replicate_id", "colony_count", "dilution_exponent", "plated_volume_ml",
                      "plating_qualifier", "calculated_cfu_ml", "log10_cfu_ml", "arquivo_origem"],
    "medicoes": ["measurement_id", "sample_id", "replicate_id", "sensor_state", "tecnica", "fonte", "arquivo_origem",
                 "contamination_status", "qc_flag", "target_bacterium", "sensor_id", "sensor_lot",
                 "experimental_batch", "surface_type", "operator_id", "measurement_date", "sample_log10_mean_cfu_ml"],
}
# colunas que viram campos próprios em outro lugar ou são derivadas: não vão para "extras"
_IGNORAR_EXTRAS = {"__arquivo", "plaqueamento_ufc_ml_media", "plaqueamento_log10_ufc_ml_media",
                   "plaqueamento_n_replicatas"}


def _agora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _py(v):
    """Converte valores numpy/pandas para tipos aceitos pelo sqlite3."""
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if v is pd.NaT or (not isinstance(v, (str, bytes)) and pd.isna(v)):
        return None
    return v


def _int_ou_none(v):
    v = _py(v)
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def conectar(caminho: str | Path = "dados/fiep.db") -> sqlite3.Connection:
    """Abre (e cria, se preciso) o banco com o esquema atualizado."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(ESQUEMA)
    atual = con.execute("SELECT MAX(versao) FROM meta_esquema").fetchone()[0]
    if atual is None:
        con.execute("INSERT INTO meta_esquema VALUES (?, ?)", (VERSAO_ESQUEMA, _agora()))
        con.commit()
    elif atual > VERSAO_ESQUEMA:
        raise RuntimeError(f"O banco usa o esquema v{atual}, mais novo que esta versão da pipeline "
                           f"(v{VERSAO_ESQUEMA}). Atualize o pacote fiep.")
    return con


def _linhas(df: pd.DataFrame, cols: list[str], extras_de: pd.DataFrame | None = None):
    base = df.reindex(columns=cols)
    extra_cols = [c for c in (extras_de if extras_de is not None else df).columns
                  if c not in cols and c not in _IGNORAR_EXTRAS]
    for i, (_, r) in enumerate(base.iterrows()):
        valores = [_py(v) for v in r.tolist()]
        ex = {c: _py(df.iloc[i][c]) for c in extra_cols if _py(df.iloc[i][c]) is not None}
        yield valores, (json.dumps(ex, ensure_ascii=False, default=str) if ex else None)


def importar(con: sqlite3.Connection, ds: Dataset, origem: str = "") -> dict:
    """Grava um Dataset no banco. Reimportar a mesma medição atualiza em vez de duplicar."""
    agora = _agora()
    avisos = "; ".join(ds.relatorio.loc[ds.relatorio["tipo"] == "aviso", "detalhe"].astype(str)) if len(ds.relatorio) else ""
    with con:
        cur = con.execute(
            "INSERT INTO importacoes (importado_em, origem, versao_pipeline, n_medicoes, n_pontos, n_amostras, avisos)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agora, str(origem), __version__, len(ds.medicoes), len(ds.pontos), len(ds.amostras), avisos or None))
        imp_id = cur.lastrowid

        novos_arquivos = 0
        for _, a in ds.arquivos.iterrows() if len(ds.arquivos) else []:
            r = con.execute("INSERT OR IGNORE INTO arquivos VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (a["sha256"], a["arquivo"], a["papel"], _py(a.get("tamanho_bytes")),
                             _py(a.get("n_linhas")), imp_id, agora))
            novos_arquivos += r.rowcount

        # amostras: completa a partir das medições quando a tabela de amostras não tem a coluna
        am = ds.amostras.copy() if len(ds.amostras) else pd.DataFrame(columns=["sample_id"])
        if len(ds.medicoes) and "sample_id" in ds.medicoes:
            faltam = set(ds.medicoes["sample_id"].dropna()) - set(am["sample_id"].dropna())
            if faltam:
                extra = ds.medicoes[ds.medicoes["sample_id"].isin(faltam)].drop_duplicates("sample_id")
                am = pd.concat([am, extra.reindex(columns=COLS["amostras"])], ignore_index=True)
        am = am.dropna(subset=["sample_id"])
        for (sid, bact, cont, logufc, lote), ex in _linhas(am, COLS["amostras"]):
            con.execute(
                """INSERT INTO amostras VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(sample_id) DO UPDATE SET
                     target_bacterium = COALESCE(excluded.target_bacterium, target_bacterium),
                     contamination_status = COALESCE(excluded.contamination_status, contamination_status),
                     sample_log10_mean_cfu_ml = COALESCE(excluded.sample_log10_mean_cfu_ml, sample_log10_mean_cfu_ml),
                     sensor_lot = COALESCE(excluded.sensor_lot, sensor_lot),
                     extras = COALESCE(excluded.extras, extras),
                     atualizado_em = excluded.atualizado_em""",
                (str(sid), bact, _int_ou_none(cont), logufc, lote, ex, agora))

        if len(ds.plaqueamento):
            pl = ds.plaqueamento.copy()
            # plaqueamento de amostra que ainda não tem medição: cria a amostra para manter a ligação
            for r in pl.drop_duplicates("sample_id").itertuples():
                con.execute("INSERT OR IGNORE INTO amostras (sample_id, target_bacterium, contamination_status, "
                            "atualizado_em) VALUES (?, ?, ?, ?)",
                            (str(r.sample_id), _py(getattr(r, "target_bacterium", None)),
                             _int_ou_none(getattr(r, "contamination_status", None)), agora))
            if "plating_replicate_id" not in pl:
                pl["plating_replicate_id"] = pl.groupby("sample_id").cumcount() + 1
            for valores, ex in _linhas(pl, COLS["plaqueamentos"]):
                valores[0] = str(valores[0])
                valores[1] = _int_ou_none(valores[1])
                con.execute("INSERT OR REPLACE INTO plaqueamentos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (*valores, ex))

        med = ds.medicoes
        ids = med["measurement_id"].astype(str).tolist()
        con.executemany("DELETE FROM pontos WHERE measurement_id = ?", [(i,) for i in ids])
        for valores, ex in _linhas(med, COLS["medicoes"]):
            valores[0] = str(valores[0])
            valores[1] = None if valores[1] is None else str(valores[1])
            valores[2] = _int_ou_none(valores[2])
            valores[7] = _int_ou_none(valores[7])
            con.execute(
                f"""INSERT INTO medicoes VALUES ({",".join("?" * (len(COLS["medicoes"]) + 2))})
                    ON CONFLICT(measurement_id) DO UPDATE SET
                    {", ".join(f"{c} = excluded.{c}" for c in COLS["medicoes"][1:])},
                    extras = excluded.extras, importacao_id = excluded.importacao_id""",
                (*valores, ex, imp_id))

        p = ds.pontos.copy()
        p["measurement_id"] = p["measurement_id"].astype(str)
        p["idx"] = p.groupby(["measurement_id", "scan_index"]).cumcount()
        for c in ("e_medido_v", "i_bruta_ua"):
            if c not in p:
                p[c] = np.nan
        p = p[["measurement_id", "scan_index", "idx", "potential_v", "current_ua", "e_medido_v", "i_bruta_ua"]]
        p = p.astype(object).where(p.notna(), None)
        con.executemany("INSERT INTO pontos VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [(r[0], int(r[1]), int(r[2]), *r[3:]) for r in p.itertuples(index=False)])

    return {"importacao_id": imp_id, "medicoes": len(med), "pontos": len(p), "amostras": len(am),
            "arquivos_novos": novos_arquivos}


def carregar(con: sqlite3.Connection, onde: str | None = None, params: tuple = ()) -> Dataset:
    """Lê o banco de volta como Dataset (para treinar ou prever).

    `onde` é um filtro SQL opcional sobre a tabela medicoes, ex.:
        carregar(con, "tecnica = ?", ("DPV",))
        carregar(con, "sample_id IN (SELECT sample_id FROM amostras WHERE target_bacterium = ?)", ("Escherichia coli",))
    """
    filtro = f"WHERE {onde}" if onde else ""
    med = pd.read_sql(f"SELECT * FROM medicoes {filtro}", con, params=params)
    if "extras" in med and med["extras"].notna().any():
        ex = pd.DataFrame([json.loads(e) if e else {} for e in med["extras"]])
        med = pd.concat([med.drop(columns="extras"), ex.drop(columns=[c for c in ex if c in med], errors="ignore")], axis=1)
    else:
        med = med.drop(columns="extras", errors="ignore")
    med = med.drop(columns="importacao_id", errors="ignore")
    ids = med["measurement_id"].tolist()
    if ids:
        con.execute("CREATE TEMP TABLE IF NOT EXISTS _ids (measurement_id TEXT PRIMARY KEY)")
        con.execute("DELETE FROM _ids")
        con.executemany("INSERT INTO _ids VALUES (?)", [(i,) for i in ids])
        pts = pd.read_sql("SELECT p.measurement_id, p.scan_index, p.potential_v, p.current_ua, p.e_medido_v, p.i_bruta_ua "
                          "FROM pontos p JOIN _ids USING (measurement_id) ORDER BY p.measurement_id, p.scan_index, p.idx", con)
    else:
        pts = pd.DataFrame(columns=["measurement_id", "scan_index", "potential_v", "current_ua", "e_medido_v", "i_bruta_ua"])
    am = pd.read_sql("SELECT * FROM amostras WHERE sample_id IN (SELECT DISTINCT sample_id FROM medicoes "
                     f"{filtro})", con, params=params).drop(columns=["extras", "atualizado_em"], errors="ignore")
    plaq = pd.read_sql("SELECT * FROM plaqueamentos", con).drop(columns="extras", errors="ignore")
    rel = pd.DataFrame({"tipo": ["origem"], "item": ["banco"], "detalhe": [f"{len(med)} medições lidas do SQLite"]})
    return Dataset(med, pts, am, rel, plaqueamento=plaq)


def gravar_qc(con: sqlite3.Connection, qc: pd.DataFrame) -> int:
    agora = _agora()
    linhas = [(str(r.measurement_id), __version__, agora, r.qc_auto, _py(r.qc_planilha), r.qc_final,
               r.qc_motivos or None, _py(r.i_max_ua)) for r in qc.itertuples()]
    with con:
        con.executemany("INSERT OR REPLACE INTO qc VALUES (?, ?, ?, ?, ?, ?, ?, ?)", linhas)
    return len(linhas)


def registrar_modelo(con: sqlite3.Connection, cartao: dict, pasta: str | Path) -> None:
    m = cartao.get("metricas_cv", {})
    with con:
        con.execute("INSERT OR REPLACE INTO modelos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (cartao["id"], cartao["criado_em"], cartao["modelo"], cartao.get("versao_pipeline"),
                     cartao.get("commit"), _py(cartao.get("limiar")), _py(m.get("balanced_accuracy")),
                     _py(m.get("sensibilidade")), _py(m.get("especificidade")), _py(m.get("roc_auc")),
                     cartao.get("n_amostras"), cartao.get("impressao_dados"), str(pasta),
                     json.dumps(cartao, ensure_ascii=False, default=str)))


def gravar_predicoes(con: sqlite3.Connection, resultado: pd.DataFrame, cartao: dict, pasta_modelo="") -> int:
    if not con.execute("SELECT 1 FROM modelos WHERE id = ?", (cartao["id"],)).fetchone():
        registrar_modelo(con, cartao, pasta_modelo)
    agora = _agora()
    linhas = []
    for r in resultado.itertuples():
        linhas.append((cartao["id"], agora, _py(getattr(r, "sample_id", None)) and str(r.sample_id),
                       _int_ou_none(getattr(r, "replicate_id", None)), _py(getattr(r, "measurement_id", None)),
                       r.status, r.resultado, _py(r.prob_contaminada), _py(r.confianca), _py(r.motivo) or None,
                       _int_ou_none(getattr(r, "rotulo_informado", None))))
    with con:
        con.executemany("INSERT INTO predicoes (modelo_id, previsto_em, sample_id, replicate_id, measurement_id, "
                        "status, resultado, prob_contaminada, confianca, motivo, rotulo_informado) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", linhas)
    return len(linhas)


def resumo(con: sqlite3.Connection) -> pd.DataFrame:
    consultas = {
        "amostras": "SELECT COUNT(*) FROM amostras",
        "amostras contaminadas": "SELECT COUNT(*) FROM amostras WHERE contamination_status = 1",
        "medições": "SELECT COUNT(*) FROM medicoes",
        "pontos": "SELECT COUNT(*) FROM pontos",
        "plaqueamentos": "SELECT COUNT(*) FROM plaqueamentos",
        "réplicas com os 3 estágios aprovados": "SELECT COUNT(*) FROM v_replicatas WHERE n_aprovadas >= 3",
        "medições reprovadas no QC (FAIL)": "SELECT COUNT(*) FROM v_qc_atual WHERE qc_final = 'FAIL'",
        "arquivos importados": "SELECT COUNT(*) FROM arquivos",
        "importações": "SELECT COUNT(*) FROM importacoes",
        "modelos registrados": "SELECT COUNT(*) FROM modelos",
        "previsões": "SELECT COUNT(*) FROM predicoes",
    }
    return pd.DataFrame([(k, con.execute(q).fetchone()[0]) for k, q in consultas.items()], columns=["item", "total"])


TABELAS_EXPORT = ["amostras", "plaqueamentos", "medicoes", "v_medicoes", "v_replicatas", "v_qc_atual",
                  "arquivos", "importacoes", "modelos", "v_predicoes", "pontos"]
LIMITE_EXCEL = 1_048_575


def exportar(con: sqlite3.Connection, destino: str | Path, formato: str = "xlsx") -> list[Path]:
    """Exporta tabelas e views para Excel (uma aba por tabela) ou para uma pasta de CSVs."""
    destino = Path(destino)
    gerados = []
    if formato == "csv":
        destino.mkdir(parents=True, exist_ok=True)
        for t in TABELAS_EXPORT:
            df = pd.read_sql(f"SELECT * FROM {t}", con)
            arq = destino / (f"{t}.csv.gz" if t == "pontos" else f"{t}.csv")
            df.to_csv(arq, index=False, encoding="utf-8-sig")
            gerados.append(arq)
        return gerados
    destino.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(destino, engine="openpyxl") as w:
        for t in TABELAS_EXPORT:
            df = pd.read_sql(f"SELECT * FROM {t}", con)
            if len(df) > LIMITE_EXCEL:
                csv = destino.with_name(destino.stem + f"_{t}.csv.gz")
                df.to_csv(csv, index=False, encoding="utf-8-sig")
                gerados.append(csv)
                pd.DataFrame({"aviso": [f"{len(df):,} linhas não cabem no Excel: exportadas em {csv.name}"]}) \
                    .to_excel(w, sheet_name=t[:31], index=False)
                continue
            df.to_excel(w, sheet_name=t[:31], index=False)
    gerados.insert(0, destino)
    return gerados
