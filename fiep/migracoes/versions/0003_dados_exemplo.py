"""dados de exemplo: o conjunto do case (dados/exemplo_case) como a empresa "Exemplo (case sintético)"

Serve para testar a plataforma e a pipeline desde o início. Para não carregar:
`fiep db migrar --sem-exemplo` (ou FIEP_SEM_EXEMPLO=1). Para tirar depois, quando chegarem os dados
reais: `fiep db exemplo --remover` (apaga só o que esta migration criou).

As tabelas são declaradas aqui mesmo (e não importadas de fiep.orm) de propósito: o modelo ORM vai
mudar, e esta migration precisa continuar funcionando como foi escrita.

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

EMPRESA = "Exemplo (case sintético)"
PASTA = Path(__file__).resolve().parents[3] / "dados" / "exemplo_case"

empresas = sa.table("empresas", sa.column("id", sa.Integer), sa.column("nome", sa.String),
                    sa.column("observacoes", sa.Text), sa.column("criado_em", sa.DateTime))
coletas = sa.table("coletas", sa.column("id", sa.Integer), sa.column("empresa_id", sa.Integer),
                   sa.column("descricao", sa.String), sa.column("origem", sa.String),
                   sa.column("versao_pipeline", sa.String), sa.column("n_medicoes", sa.Integer),
                   sa.column("n_amostras", sa.Integer), sa.column("criado_em", sa.DateTime))
amostras = sa.table("amostras", *(sa.column(c) for c in (
    "sample_id", "empresa_id", "coleta_id", "target_bacterium", "contamination_status", "sample_log10_mean_cfu_ml",
    "sensor_lot")), sa.column("extras", sa.JSON), sa.column("atualizado_em", sa.DateTime))
plaqueamentos = sa.table("plaqueamentos", *(sa.column(c) for c in (
    "sample_id", "plating_replicate_id", "colony_count", "dilution_exponent", "plated_volume_ml",
    "plating_qualifier", "calculated_cfu_ml", "log10_cfu_ml", "arquivo_origem")))
medicoes = sa.table("medicoes", *(sa.column(c) for c in (
    "measurement_id", "sample_id", "replicate_id", "sensor_state", "tecnica", "fonte", "arquivo_origem",
    "contamination_status", "qc_flag", "sensor_id", "sensor_lot", "experimental_batch", "surface_type",
    "operator_id", "measurement_date", "coleta_id")))
curvas = sa.table("curvas", sa.column("measurement_id"), sa.column("n_pontos"),
                  sa.column("potential_v", sa.JSON), sa.column("current_ua", sa.JSON),
                  sa.column("scan_index", sa.JSON), sa.column("e_medido_v", sa.JSON), sa.column("i_bruta_ua", sa.JSON))


def _vazio(v):
    try:
        import math
        return v is None or (isinstance(v, float) and math.isnan(v))
    except TypeError:
        return False


def _v(v):
    if _vazio(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def upgrade() -> None:
    cfg = op.get_context().config
    if not cfg.attributes.get("dados_exemplo", True) or os.environ.get("FIEP_SEM_EXEMPLO") == "1":
        print("0003: dados de exemplo pulados")
        return
    if not PASTA.exists():
        print(f"0003: {PASTA} não encontrada; dados de exemplo pulados")
        return
    import pandas as pd

    from fiep.ingest import ingerir
    ds = ingerir(PASTA)
    bind = op.get_bind()
    agora = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    bind.execute(empresas.insert().values(nome=EMPRESA, criado_em=agora,
                                          observacoes="Dados sintéticos do case, para testes. Remover com "
                                                      "`fiep db exemplo --remover`."))
    emp_id = bind.execute(sa.select(empresas.c.id).where(empresas.c.nome == EMPRESA)).scalar_one()
    bind.execute(coletas.insert().values(empresa_id=emp_id, descricao="Conjunto de demonstração (case)",
                                         origem="migration 0003", versao_pipeline="0003",
                                         n_medicoes=len(ds.medicoes), n_amostras=ds.medicoes["sample_id"].nunique(),
                                         criado_em=agora))
    col_id = bind.execute(sa.select(sa.func.max(coletas.c.id)).where(coletas.c.empresa_id == emp_id)).scalar_one()

    m = ds.medicoes
    am = m.drop_duplicates("sample_id")
    extras = ds.amostras.set_index("sample_id") if len(ds.amostras) else pd.DataFrame()
    op.bulk_insert(amostras, [{
        "sample_id": str(r.sample_id), "empresa_id": emp_id, "coleta_id": col_id,
        "target_bacterium": _v(r.target_bacterium), "contamination_status": _v(r.contamination_status),
        "sample_log10_mean_cfu_ml": _v(r.sample_log10_mean_cfu_ml), "sensor_lot": _v(r.sensor_lot),
        "extras": {k: _v(v) for k, v in extras.loc[r.sample_id].items() if k.startswith("plaqueamento_")
                   and not _vazio(v)} if r.sample_id in extras.index else None,
        "atualizado_em": agora} for r in am.itertuples()])
    if len(ds.plaqueamento):
        pl = ds.plaqueamento.copy()
        if "plating_replicate_id" not in pl:
            pl["plating_replicate_id"] = pl.groupby("sample_id").cumcount() + 1
        cols = ["sample_id", "plating_replicate_id", "colony_count", "dilution_exponent", "plated_volume_ml",
                "plating_qualifier", "calculated_cfu_ml", "log10_cfu_ml", "arquivo_origem"]
        pl = pl[pl["sample_id"].isin(set(am["sample_id"]))].reindex(columns=cols)
        op.bulk_insert(plaqueamentos, [{c: (str(r[c]) if c == "sample_id" else _v(r[c])) for c in cols}
                                       for _, r in pl.iterrows()])
    cols = ["measurement_id", "sample_id", "replicate_id", "sensor_state", "tecnica", "fonte", "arquivo_origem",
            "contamination_status", "qc_flag", "sensor_id", "sensor_lot", "experimental_batch", "surface_type",
            "operator_id", "measurement_date"]
    linhas = []
    for _, r in m.reindex(columns=cols).iterrows():
        d = {c: _v(r[c]) for c in cols}
        d["replicate_id"] = None if d["replicate_id"] is None else str(d["replicate_id"])
        d["sample_id"] = str(d["sample_id"])
        d["coleta_id"] = col_id
        linhas.append(d)
    op.bulk_insert(medicoes, linhas)
    pts = ds.pontos
    op.bulk_insert(curvas, [{
        "measurement_id": str(mid), "n_pontos": len(g), "potential_v": g["potential_v"].astype(float).tolist(),
        "current_ua": g["current_ua"].astype(float).tolist(), "scan_index": g["scan_index"].astype(int).tolist(),
        "e_medido_v": None, "i_bruta_ua": None} for mid, g in pts.groupby("measurement_id", sort=False)])
    print(f"0003: {len(am)} amostras e {len(m)} medições de exemplo carregadas")


def downgrade() -> None:
    bind = op.get_bind()
    emp = bind.execute(sa.select(empresas.c.id).where(empresas.c.nome == EMPRESA)).scalar()
    if emp is None:
        return
    remover_exemplo(bind, emp)


def remover_exemplo(bind, emp_id: int) -> None:
    """Apaga as amostras, medições e coletas da empresa de exemplo (usado também por `fiep db exemplo --remover`)."""
    ids = [r[0] for r in bind.execute(sa.text("SELECT id FROM coletas WHERE empresa_id = :e"), {"e": emp_id})]
    for cid in ids:
        sub = "SELECT measurement_id FROM medicoes WHERE coleta_id = :c"
        bind.execute(sa.text(f"DELETE FROM curvas WHERE measurement_id IN ({sub})"), {"c": cid})
        bind.execute(sa.text(f"DELETE FROM qc WHERE measurement_id IN ({sub})"), {"c": cid})
        bind.execute(sa.text("DELETE FROM medicoes WHERE coleta_id = :c"), {"c": cid})
        bind.execute(sa.text("DELETE FROM plaqueamentos WHERE sample_id IN "
                             "(SELECT sample_id FROM amostras WHERE coleta_id = :c)"), {"c": cid})
        bind.execute(sa.text("DELETE FROM amostras WHERE coleta_id = :c"), {"c": cid})
        bind.execute(sa.text("DELETE FROM arquivos WHERE coleta_id = :c"), {"c": cid})
        bind.execute(sa.text("DELETE FROM coletas WHERE id = :c"), {"c": cid})
    bind.execute(sa.text("DELETE FROM empresas WHERE id = :e"), {"e": emp_id})
