"""Conversão do banco antigo (SQLite criado antes do ORM, com a tabela `meta_esquema`).

Quando `fiep.orm.migrar` encontra um banco desses no lugar do novo, ele:
1. renomeia o arquivo para `<nome>.antigo-AAAAMMDD-HHMMSS.db` (nada é apagado);
2. cria o banco novo pelas migrations;
3. copia para ele amostras, medições, pontos, plaqueamentos, QC, modelos e previsões do antigo.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# esquema da versão antiga (fiep/db.py até o commit 5ff7889), usado para reconhecer e testar a conversão
ESQUEMA_V1 = """
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


def tabelas(caminho: Path) -> set[str]:
    if not caminho.exists() or caminho.stat().st_size == 0:
        return set()
    con = sqlite3.connect(caminho)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        con.close()


def eh_antigo(caminho: Path) -> bool:
    t = tabelas(caminho)
    return "meta_esquema" in t and "alembic_version" not in t


def ler(caminho: Path):
    """Lê o banco antigo: (Dataset, qc, modelos, predicoes)."""
    from .ingest import Dataset
    con = sqlite3.connect(caminho)
    try:
        q = lambda sql: pd.read_sql(sql, con)  # noqa: E731
        med = q("SELECT * FROM medicoes")
        if "extras" in med:
            ex = pd.DataFrame([json.loads(e) if e else {} for e in med["extras"]], index=med.index)
            med = pd.concat([med.drop(columns="extras"), ex.drop(columns=[c for c in ex if c in med], errors="ignore")],
                            axis=1)
        med = med.drop(columns=["importacao_id"], errors="ignore")
        pts = q("SELECT measurement_id, scan_index, potential_v, current_ua, e_medido_v, i_bruta_ua FROM pontos "
                "ORDER BY measurement_id, scan_index, idx")
        am = q("SELECT * FROM amostras").drop(columns=["extras", "atualizado_em"], errors="ignore")
        plaq = q("SELECT * FROM plaqueamentos").drop(columns="extras", errors="ignore")
        arq = q("SELECT arquivo, papel, sha256, tamanho_bytes, n_linhas FROM arquivos")
        qc = q("SELECT measurement_id, qc_auto, qc_planilha, qc_final, qc_motivos, i_max_ua FROM v_qc_atual")
        modelos = q("SELECT * FROM modelos")
        pred = q("SELECT * FROM predicoes")
    finally:
        con.close()
    rel = pd.DataFrame({"tipo": ["origem"], "item": ["banco antigo"], "detalhe": [str(caminho)]})
    return Dataset(med, pts, am, rel, plaqueamento=plaq, arquivos=arq), qc, modelos, pred


def converter(antigo: Path, s) -> dict:
    """Copia o conteúdo do banco antigo para a sessão `s` (banco novo, já migrado)."""
    from . import db
    ds, qc, modelos, pred = ler(antigo)
    res = {"medicoes": 0, "modelos": 0, "previsoes": 0}
    if len(ds.medicoes):
        r = db.importar(s, ds, origem=f"banco antigo ({antigo.name})", descricao="Importado do banco antigo")
        res["medicoes"] = r["medicoes"]
        if len(qc):
            db.gravar_qc(s, qc)
    for _, m in modelos.iterrows():
        try:
            cartao = json.loads(m["cartao"]) if m.get("cartao") else {"id": m["id"], "modelo": m.get("algoritmo")}
            db.registrar_modelo(s, cartao, m.get("caminho") or "")
            res["modelos"] += 1
        except Exception as e:  # noqa: BLE001
            log.warning("Modelo %s não convertido: %s", m.get("id"), e)
    if len(pred):
        from .orm import ModeloML
        for mid, g in pred.groupby("modelo_id"):
            if s.get(ModeloML, mid) is None:
                continue
            db.gravar_predicoes(s, g.drop(columns=["id", "modelo_id", "previsto_em"], errors="ignore"),
                                {"id": mid})
            res["previsoes"] += len(g)
    return res


def nome_backup(caminho: Path) -> Path:
    return caminho.with_name(f"{caminho.stem}.antigo-{dt.datetime.now():%Y%m%d-%H%M%S}{caminho.suffix}")
