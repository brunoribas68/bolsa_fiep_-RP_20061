"""views de consulta: v_qc_atual, v_medicoes, v_replicatas, v_predicoes

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

VIEWS = ["v_predicoes", "v_replicatas", "v_medicoes", "v_qc_atual"]


def upgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    juntar = "GROUP_CONCAT(sensor_state, ', ')" if sqlite else "STRING_AGG(sensor_state, ', ')"
    op.execute("""
        CREATE VIEW v_qc_atual AS
        SELECT q.* FROM qc q
        WHERE q.avaliado_em = (SELECT MAX(q2.avaliado_em) FROM qc q2 WHERE q2.measurement_id = q.measurement_id)""")
    op.execute("""
        CREATE VIEW v_medicoes AS
        SELECT m.measurement_id, m.sample_id, m.replicate_id, m.sensor_state, m.tecnica, m.fonte,
               m.arquivo_origem, COALESCE(m.contamination_status, a.contamination_status) AS contamination_status,
               a.target_bacterium, a.conjunto, m.sensor_lot, m.experimental_batch, m.surface_type,
               m.measurement_date, m.coleta_id, m.qc_flag AS qc_planilha, q.qc_auto, q.qc_final, q.qc_motivos,
               c.n_pontos
        FROM medicoes m
        LEFT JOIN amostras a ON a.sample_id = m.sample_id
        LEFT JOIN v_qc_atual q ON q.measurement_id = m.measurement_id
        LEFT JOIN curvas c ON c.measurement_id = m.measurement_id""")
    op.execute(f"""
        CREATE VIEW v_replicatas AS
        SELECT sample_id, replicate_id,
               COUNT(*) AS n_medicoes,
               {juntar} AS estagios,
               SUM(CASE WHEN qc_final = 'PASS' OR (qc_final IS NULL AND COALESCE(qc_planilha, 'PASS') = 'PASS')
                        THEN 1 ELSE 0 END) AS n_aprovadas,
               MAX(contamination_status) AS contamination_status
        FROM v_medicoes
        GROUP BY sample_id, replicate_id""")
    op.execute("""
        CREATE VIEW v_predicoes AS
        SELECT p.*, m.algoritmo, m.balanced_accuracy AS modelo_balanced_accuracy
        FROM predicoes p JOIN modelos m ON m.id = p.modelo_id""")


def downgrade() -> None:
    for v in VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {v}")
