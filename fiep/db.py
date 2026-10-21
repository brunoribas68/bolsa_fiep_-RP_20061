"""Banco de dados do projeto, sobre o modelo ORM (`fiep/orm/`) e as migrations (`fiep/migracoes/`).

Funções usadas pela pipeline, pela linha de comando e pela API:

    s = conectar("dados/fiep.db")        # aplica as migrations e abre uma sessão (SQLite ou FIEP_DB_URL)
    importar(s, ds, ...)                 # grava um Dataset (reimportar atualiza, não duplica)
    carregar(s, "tecnica = 'DPV'")       # lê de volta como Dataset, para treinar ou prever
    gravar_qc / registrar_modelo / gravar_predicoes / resumo / exportar / sql

Views para consulta: v_medicoes, v_replicatas, v_qc_atual, v_predicoes.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import __version__
from .ingest import Dataset
from .orm import (Amostra, Arquivo, Coleta, Curva, Empresa, Medicao, ModeloML, Plaqueamento, Predicao,
                  ResultadoQC, fabrica_sessoes, migrar)

EMPRESA_EXEMPLO = "Exemplo (case sintético)"
PASTA_EXEMPLO = Path(__file__).resolve().parent.parent / "dados" / "exemplo_case"

# colunas da medição com campo próprio; o resto vai para `extras` (JSON)
CAMPOS_MEDICAO = ["sample_id", "replicate_id", "sensor_state", "tecnica", "fonte", "arquivo_origem",
                  "contamination_status", "qc_flag", "sensor_id", "sensor_lot", "experimental_batch",
                  "surface_type", "operator_id", "measurement_date"]
CAMPOS_AMOSTRA = ["target_bacterium", "contamination_status", "sample_log10_mean_cfu_ml", "surface_type", "sensor_lot",
                  "conjunto"]
# derivadas ou já guardadas em outro lugar: não vão para extras
_IGNORAR = {"__arquivo", "measurement_id", "target_bacterium", "sample_log10_mean_cfu_ml", "conjunto",
            "plaqueamento_ufc_ml_media", "plaqueamento_log10_ufc_ml_media", "plaqueamento_n_replicatas"}
CAMPOS_PLAQ = ["colony_count", "dilution_exponent", "plated_volume_ml", "plating_qualifier", "calculated_cfu_ml",
               "log10_cfu_ml", "arquivo_origem"]


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _py(v):
    """numpy/pandas -> tipos simples (None para vazio)."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, str):
        return v.strip() or None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _int(v):
    v = _py(v)
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _str(v):
    v = _py(v)
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


# ----------------------------------------------------------------------------- conexão

def conectar(caminho: str | Path | None = None, dados_exemplo: bool = False) -> Session:
    """Aplica as migrations pendentes e devolve uma sessão. Sem caminho: FIEP_DB_URL ou dados/fiep.db.

    `dados_exemplo=True` carrega o case de demonstração quando o banco é criado."""
    migrar(caminho, dados_exemplo=dados_exemplo)
    return fabrica_sessoes(caminho)()


def sql(s: Session, consulta: str, params: tuple | dict = ()) -> pd.DataFrame:
    """Consulta SQL livre (ex.: nas views). Parâmetros com `?` no SQLite."""
    res = s.connection().exec_driver_sql(consulta, params) if params else s.connection().exec_driver_sql(consulta)
    return pd.DataFrame(res.fetchall(), columns=list(res.keys()))


# ----------------------------------------------------------------------------- importar

def _empresa(s: Session, nome: str | None) -> Empresa | None:
    if not nome:
        return None
    e = s.scalar(select(Empresa).where(Empresa.nome == nome))
    if e is None:
        e = Empresa(nome=nome)
        s.add(e)
        s.flush()
    return e


def importar(s: Session, ds: Dataset, origem: str = "", coleta: Coleta | None = None, empresa: str | None = None,
             conjunto: str | None = None, usuario_id: int | None = None, descricao: str | None = None,
             caminhos: dict | None = None) -> dict:
    """Grava um Dataset. Medições e amostras existentes são atualizadas (não duplicam); arquivos
    já importados (mesmo SHA-256) não são registrados de novo. Cria uma Coleta se não for passada.

    `conjunto` (treino/validacao/teste) fixa o conjunto das amostras desta coleta; `caminhos`
    ({nome do arquivo: onde ficou guardado}) registra o original de cada arquivo."""
    avisos = ds.relatorio.loc[ds.relatorio["tipo"] == "aviso", "detalhe"].astype(str).tolist() \
        if len(ds.relatorio) else []
    emp = _empresa(s, empresa)
    if coleta is None:
        coleta = Coleta(empresa_id=emp.id if emp else None, origem=str(origem) or None, conjunto=conjunto,
                        descricao=descricao, criado_por_id=usuario_id)
        s.add(coleta)
    coleta.versao_pipeline = __version__
    coleta.avisos = (coleta.avisos or []) + avisos or None
    s.flush()
    emp_id = coleta.empresa_id

    # arquivos
    novos = 0
    if len(ds.arquivos):
        shas = set(ds.arquivos["sha256"])
        ja = set(s.scalars(select(Arquivo.sha256).where(Arquivo.sha256.in_(shas))))
        for a in ds.arquivos.drop_duplicates("sha256").itertuples():
            if a.sha256 in ja:
                continue
            s.add(Arquivo(sha256=a.sha256, arquivo=a.arquivo, papel=a.papel, tamanho_bytes=_int(a.tamanho_bytes),
                          n_linhas=_int(a.n_linhas), coleta_id=coleta.id,
                          caminho=(caminhos or {}).get(a.arquivo)))
            novos += 1

    med = ds.medicoes.copy()
    med["sample_id"] = med["sample_id"].map(_str)
    # amostras: dados da tabela de amostras + o que vier nas medições
    am = ds.amostras.copy() if len(ds.amostras) else pd.DataFrame(columns=["sample_id"])
    am["sample_id"] = am["sample_id"].map(_str)
    por_med = med.dropna(subset=["sample_id"]).drop_duplicates("sample_id").set_index("sample_id")
    ids_am = sorted(set(am["sample_id"].dropna()) | set(por_med.index))
    am = am.dropna(subset=["sample_id"]).drop_duplicates("sample_id").set_index("sample_id")
    existentes = {a.sample_id: a for a in s.scalars(select(Amostra).where(Amostra.sample_id.in_(ids_am)))} \
        if ids_am else {}
    for sid in ids_am:
        a = existentes.get(sid) or Amostra(sample_id=sid, empresa_id=emp_id, coleta_id=coleta.id)
        if sid not in existentes:
            s.add(a)
        for campo in CAMPOS_AMOSTRA:
            v = am.at[sid, campo] if sid in am.index and campo in am else None
            if _py(v) is None and sid in por_med.index and campo in por_med:
                v = por_med.at[sid, campo]
            v = _int(v) if campo == "contamination_status" else _py(v)
            if campo == "conjunto" and conjunto:
                v = conjunto
            if v is not None:
                setattr(a, campo, v)
        if conjunto and a.conjunto is None:
            a.conjunto = conjunto
        ex = {k: _py(v) for k, v in am.loc[sid].items() if k not in CAMPOS_AMOSTRA and _py(v) is not None} \
            if sid in am.index else {}
        if ex:
            a.extras = {**(a.extras or {}), **ex}
        a.atualizado_por_id = usuario_id or a.atualizado_por_id
    s.flush()

    # plaqueamento
    if len(ds.plaqueamento):
        pl = ds.plaqueamento.copy()
        pl["sample_id"] = pl["sample_id"].map(_str)
        if "plating_replicate_id" not in pl:
            pl["plating_replicate_id"] = pl.groupby("sample_id").cumcount() + 1
        for sid in set(pl["sample_id"].dropna()) - set(ids_am):
            s.add(Amostra(sample_id=sid, empresa_id=emp_id, coleta_id=coleta.id))
        s.flush()
        for _, r in pl.dropna(subset=["sample_id"]).iterrows():
            p = s.get(Plaqueamento, (r["sample_id"], _int(r["plating_replicate_id"]))) or \
                Plaqueamento(sample_id=r["sample_id"], plating_replicate_id=_int(r["plating_replicate_id"]))
            s.add(p)
            for c in CAMPOS_PLAQ:
                if c in r:
                    setattr(p, c, _py(r[c]))

    # medições + curvas
    mids = med["measurement_id"].map(_str).tolist()
    exist_m = {}
    for i in range(0, len(mids), 500):
        exist_m.update({m.measurement_id: m for m in
                        s.scalars(select(Medicao).where(Medicao.measurement_id.in_(mids[i:i + 500])))})
        s.execute(delete(Curva).where(Curva.measurement_id.in_(mids[i:i + 500])))
    extra_cols = [c for c in med.columns if c not in CAMPOS_MEDICAO and c not in _IGNORAR]
    for mid, (_, r) in zip(mids, med.iterrows()):
        m = exist_m.get(mid) or Medicao(measurement_id=mid)
        if mid not in exist_m:
            s.add(m)
        for c in CAMPOS_MEDICAO:
            v = r.get(c)
            setattr(m, c, _int(v) if c == "contamination_status" else
                    _str(v) if c in ("sample_id", "replicate_id") else _py(v))
        ex = {c: _py(r[c]) for c in extra_cols if _py(r[c]) is not None}
        m.extras = ex or None
        m.coleta_id = coleta.id
    s.flush()
    pts = ds.pontos
    n_pts = 0
    for mid, g in pts.groupby(pts["measurement_id"].map(_str), sort=False):
        def col(c, conv=float):
            if c not in g or g[c].isna().all():
                return None
            return [None if pd.isna(x) else conv(x) for x in g[c]]
        s.add(Curva(measurement_id=mid, n_pontos=len(g), potential_v=col("potential_v"),
                    current_ua=col("current_ua"), scan_index=col("scan_index", int),
                    e_medido_v=col("e_medido_v"), i_bruta_ua=col("i_bruta_ua")))
        n_pts += len(g)
    coleta.n_medicoes = (coleta.n_medicoes or 0) + len(med)
    coleta.n_amostras = s.scalar(select(func.count()).select_from(Amostra).where(Amostra.coleta_id == coleta.id))
    s.commit()
    return {"importacao_id": coleta.id, "coleta_id": coleta.id, "medicoes": len(med), "pontos": n_pts,
            "amostras": len(ids_am), "arquivos_novos": novos}


# ----------------------------------------------------------------------------- carregar

_SELECT_MEDICOES = """
SELECT m.measurement_id, m.sample_id, m.replicate_id, m.sensor_state, m.tecnica, m.fonte, m.arquivo_origem,
       COALESCE(m.contamination_status, a.contamination_status) AS contamination_status, m.qc_flag,
       a.target_bacterium, m.sensor_id, COALESCE(m.sensor_lot, a.sensor_lot) AS sensor_lot,
       m.experimental_batch, COALESCE(m.surface_type, a.surface_type) AS surface_type, m.operator_id,
       m.measurement_date, a.sample_log10_mean_cfu_ml, a.conjunto, a.empresa_id, m.coleta_id, m.extras
FROM medicoes m LEFT JOIN amostras a ON a.sample_id = m.sample_id"""


def carregar(s: Session, onde: str | None = None, params: tuple = ()) -> Dataset:
    """Lê o banco como Dataset. `onde` é um filtro SQL sobre as colunas da medição, ex.:
        carregar(s, "tecnica = ?", ("DPV",))
        carregar(s, "empresa_id = 2 AND conjunto IS NULL")
    """
    consulta = f"SELECT * FROM ({_SELECT_MEDICOES}) t" + (f" WHERE {onde}" if onde else "")
    med = sql(s, consulta, params)
    if "extras" in med:
        ex = [json.loads(e) if isinstance(e, str) else (e or {}) for e in med["extras"]]
        ex = pd.DataFrame(ex, index=med.index)
        med = pd.concat([med.drop(columns="extras"), ex.drop(columns=[c for c in ex if c in med], errors="ignore")],
                        axis=1)
    ids = med["measurement_id"].tolist()
    partes = []
    for i in range(0, len(ids), 500):
        for c in s.scalars(select(Curva).where(Curva.measurement_id.in_(ids[i:i + 500]))):
            n = c.n_pontos
            partes.append(pd.DataFrame({
                "measurement_id": [c.measurement_id] * n,
                "scan_index": c.scan_index or [1] * n,
                "potential_v": c.potential_v, "current_ua": c.current_ua,
                "e_medido_v": c.e_medido_v or [np.nan] * n, "i_bruta_ua": c.i_bruta_ua or [np.nan] * n}))
    pts = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
        columns=["measurement_id", "scan_index", "potential_v", "current_ua", "e_medido_v", "i_bruta_ua"])
    pts = pts.astype({"potential_v": float, "current_ua": float, "e_medido_v": float, "i_bruta_ua": float})
    sids = sorted(set(med["sample_id"].dropna()))
    am = sql(s, "SELECT sample_id, target_bacterium, contamination_status, sample_log10_mean_cfu_ml, sensor_lot, "
                "conjunto FROM amostras") if sids else pd.DataFrame(columns=["sample_id"])
    am = am[am["sample_id"].isin(sids)].reset_index(drop=True)
    plaq = sql(s, "SELECT * FROM plaqueamentos").drop(columns="extras", errors="ignore")
    plaq = plaq[plaq["sample_id"].isin(sids)].reset_index(drop=True)
    rel = pd.DataFrame({"tipo": ["origem"], "item": ["banco"], "detalhe": [f"{len(med)} medições lidas do banco"]})
    return Dataset(med, pts, am, rel, plaqueamento=plaq)


# ----------------------------------------------------------------------------- QC, modelos, previsões

def gravar_qc(s: Session, qc: pd.DataFrame) -> int:
    agora = _agora()
    for r in qc.itertuples():
        q = s.get(ResultadoQC, (str(r.measurement_id), __version__)) or \
            ResultadoQC(measurement_id=str(r.measurement_id), versao_pipeline=__version__)
        q.avaliado_em, q.qc_auto, q.qc_planilha = agora, r.qc_auto, _py(r.qc_planilha)
        q.qc_final, q.qc_motivos, q.i_max_ua = r.qc_final, r.qc_motivos or None, _py(r.i_max_ua)
        s.add(q)
    s.commit()
    return len(qc)


def registrar_modelo(s: Session, cartao: dict, pasta: str | Path) -> ModeloML:
    m = cartao.get("metricas_cv", {})
    mod = s.get(ModeloML, cartao["id"]) or ModeloML(id=cartao["id"])
    mod.criado_em, mod.algoritmo = cartao.get("criado_em"), cartao.get("modelo")
    mod.versao_pipeline, mod.commit_codigo = cartao.get("versao_pipeline"), cartao.get("commit")
    mod.limiar, mod.balanced_accuracy = _py(cartao.get("limiar")), _py(m.get("balanced_accuracy"))
    mod.sensibilidade, mod.especificidade = _py(m.get("sensibilidade")), _py(m.get("especificidade"))
    mod.roc_auc, mod.n_amostras = _py(m.get("roc_auc")), _int(cartao.get("n_amostras"))
    mod.impressao_dados, mod.caminho = cartao.get("impressao_dados"), str(pasta)
    mod.cartao = json.loads(json.dumps(cartao, default=str))
    s.add(mod)
    s.commit()
    return mod


def gravar_predicoes(s: Session, resultado: pd.DataFrame, cartao: dict, pasta_modelo="",
                     usuario_id: int | None = None) -> int:
    if s.get(ModeloML, cartao["id"]) is None:
        registrar_modelo(s, cartao, pasta_modelo)
    agora = _agora()
    for r in resultado.to_dict(orient="records"):
        s.add(Predicao(modelo_id=cartao["id"], previsto_em=agora, sample_id=_str(r.get("sample_id")),
                       replicate_id=_str(r.get("replicate_id")), measurement_id=_py(r.get("measurement_id")),
                       status=_py(r.get("status")), resultado=_py(r.get("resultado")),
                       prob_contaminada=_py(r.get("prob_contaminada")), confianca=_py(r.get("confianca")),
                       log10_ufc_ml_estimado=_py(r.get("log10_ufc_ml_estimado")),
                       nivel_contaminacao=_py(r.get("nivel_contaminacao")), motivo=_py(r.get("motivo")),
                       rotulo_informado=_int(r.get("rotulo_informado")), usuario_id=usuario_id))
    s.commit()
    return len(resultado)


# ----------------------------------------------------------------------------- resumo e exportação

def resumo(s: Session) -> pd.DataFrame:
    consultas = {
        "empresas": "SELECT COUNT(*) FROM empresas",
        "coletas": "SELECT COUNT(*) FROM coletas",
        "amostras": "SELECT COUNT(*) FROM amostras",
        "amostras contaminadas": "SELECT COUNT(*) FROM amostras WHERE contamination_status = 1",
        "amostras sem rótulo": "SELECT COUNT(*) FROM amostras WHERE contamination_status IS NULL",
        "medições": "SELECT COUNT(*) FROM medicoes",
        "pontos": "SELECT COALESCE(SUM(n_pontos), 0) FROM curvas",
        "plaqueamentos": "SELECT COUNT(*) FROM plaqueamentos",
        "réplicas com os 3 estágios aprovados": "SELECT COUNT(*) FROM v_replicatas WHERE n_aprovadas >= 3",
        "medições reprovadas no QC (FAIL)": "SELECT COUNT(*) FROM v_qc_atual WHERE qc_final = 'FAIL'",
        "arquivos importados": "SELECT COUNT(*) FROM arquivos",
        "modelos registrados": "SELECT COUNT(*) FROM modelos",
        "previsões": "SELECT COUNT(*) FROM predicoes",
    }
    return pd.DataFrame([(k, sql(s, q).iloc[0, 0]) for k, q in consultas.items()], columns=["item", "total"])


TABELAS_EXPORT = ["empresas", "coletas", "amostras", "plaqueamentos", "medicoes", "v_medicoes", "v_replicatas",
                  "v_qc_atual", "arquivos", "modelos", "v_predicoes"]
LIMITE_EXCEL = 1_048_575


def _pontos(s: Session) -> pd.DataFrame:
    d = carregar(s).pontos
    return d


def exportar(s: Session, destino: str | Path, formato: str = "xlsx") -> list[Path]:
    """Exporta tabelas, views e os pontos das curvas para Excel (uma aba por tabela) ou CSVs."""
    destino = Path(destino)
    tabelas = {t: sql(s, f"SELECT * FROM {t}") for t in TABELAS_EXPORT}
    for t in ("coletas", "amostras", "medicoes", "modelos", "plaqueamentos"):
        for c in ("avisos", "extras", "cartao"):
            if c in tabelas[t]:
                tabelas[t][c] = tabelas[t][c].map(lambda v: v if v is None or isinstance(v, str) else json.dumps(v))
    tabelas["pontos"] = _pontos(s)
    gerados = []
    if formato == "csv":
        destino.mkdir(parents=True, exist_ok=True)
        for t, df in tabelas.items():
            arq = destino / (f"{t}.csv.gz" if t == "pontos" else f"{t}.csv")
            df.to_csv(arq, index=False, encoding="utf-8-sig")
            gerados.append(arq)
        return gerados
    destino.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(destino, engine="openpyxl") as w:
        for t, df in tabelas.items():
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


# ----------------------------------------------------------------------------- dados de exemplo

def carregar_exemplo(s: Session) -> dict | None:
    """Carrega o case de demonstração como a empresa de exemplo (se ainda não estiver no banco)."""
    from .ingest import ingerir
    if s.scalar(select(Empresa).where(Empresa.nome == EMPRESA_EXEMPLO)) is not None:
        return None
    return importar(s, ingerir(PASTA_EXEMPLO), origem="dados/exemplo_case", empresa=EMPRESA_EXEMPLO,
                    descricao="Conjunto de demonstração (case)")


def remover_exemplo(s: Session) -> bool:
    """Apaga a empresa de exemplo e tudo o que veio com ela."""
    import importlib.util
    emp = s.scalar(select(Empresa).where(Empresa.nome == EMPRESA_EXEMPLO))
    if emp is None:
        return False
    caminho = Path(__file__).resolve().parent / "migracoes" / "versions" / "0003_dados_exemplo.py"
    spec = importlib.util.spec_from_file_location("_m0003", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.remover_exemplo(s.connection(), emp.id)
    s.commit()
    return True

