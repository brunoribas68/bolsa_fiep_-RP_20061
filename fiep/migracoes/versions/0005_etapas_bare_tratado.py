"""ensaios: etapas bare e tratado; elemento de captura opcional (não existe antes do branco)

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ensaios", schema=None) as b:
        b.drop_constraint("tipo", type_="check")
        b.create_check_constraint("tipo", "tipo IN ('bare', 'tratado', 'branco', 'alvo', 'negativo')")
        b.alter_column("elemento_captura", existing_type=sa.String(length=120), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM ensaios WHERE tipo IN ('bare', 'tratado')")
    with op.batch_alter_table("ensaios", schema=None) as b:
        b.drop_constraint("tipo", type_="check")
        b.create_check_constraint("tipo", "tipo IN ('branco', 'alvo', 'negativo')")
        b.alter_column("elemento_captura", existing_type=sa.String(length=120), nullable=False)
