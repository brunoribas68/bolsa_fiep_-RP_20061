"""base do genossensor: tabela `ensaios` (branco/alvo/negativo, pico, eletrodo, concentração)

Dicionário: docs/DICIONARIO_DADOS.md.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ensaios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=True),
    sa.Column('coleta_id', sa.Integer(), nullable=True),
    sa.Column('eletrodo_id', sa.String(length=60), nullable=False),
    sa.Column('canal', sa.String(length=60), nullable=True),
    sa.Column('elemento_captura', sa.String(length=120), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('alvo', sa.String(length=120), nullable=True),
    sa.Column('bacteria', sa.String(length=120), nullable=True),
    sa.Column('concentracao', sa.Float(), nullable=False),
    sa.Column('unidade', sa.String(length=20), nullable=False),
    sa.Column('branco_id', sa.Integer(), nullable=True),
    sa.Column('tecnica', sa.String(length=20), nullable=False),
    sa.Column('tipo_eletrodo', sa.String(length=60), nullable=True),
    sa.Column('tratamento', sa.String(length=60), nullable=True),
    sa.Column('procedimento', sa.String(length=300), nullable=True),
    sa.Column('medido_em', sa.DateTime(), nullable=True),
    sa.Column('e_pico_v', sa.Float(), nullable=True),
    sa.Column('i_pico_ua', sa.Float(), nullable=True),
    sa.Column('i_base_ua', sa.Float(), nullable=True),
    sa.Column('altura_ua', sa.Float(), nullable=True),
    sa.Column('largura_v', sa.Float(), nullable=True),
    sa.Column('area_uav', sa.Float(), nullable=True),
    sa.Column('potential_v', sa.JSON(), nullable=True),
    sa.Column('current_ua', sa.JSON(), nullable=True),
    sa.Column('qc_flag', sa.String(length=20), nullable=True),
    sa.Column('conjunto', sa.String(length=20), nullable=True),
    sa.Column('arquivo', sa.String(length=300), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.CheckConstraint("conjunto IS NULL OR conjunto IN ('treino', 'validacao', 'teste')", name=op.f('ck_ensaios_conjunto')),
    sa.CheckConstraint("tipo = 'alvo' OR concentracao = 0", name=op.f('ck_ensaios_sem_alvo_conc_zero')),
    sa.CheckConstraint("tipo IN ('branco', 'alvo', 'negativo')", name=op.f('ck_ensaios_tipo')),
    sa.CheckConstraint('concentracao >= 0', name=op.f('ck_ensaios_concentracao')),
    sa.ForeignKeyConstraint(['branco_id'], ['ensaios.id'], name=op.f('fk_ensaios_branco_id_ensaios'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['coleta_id'], ['coletas.id'], name=op.f('fk_ensaios_coleta_id_coletas'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name=op.f('fk_ensaios_empresa_id_empresas')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ensaios')),
    sa.UniqueConstraint('sha256', name=op.f('uq_ensaios_sha256'))
    )
    with op.batch_alter_table('ensaios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ensaios_coleta_id'), ['coleta_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ensaios_eletrodo_id'), ['eletrodo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ensaios_empresa_id'), ['empresa_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('ensaios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ensaios_empresa_id'))
        batch_op.drop_index(batch_op.f('ix_ensaios_eletrodo_id'))
        batch_op.drop_index(batch_op.f('ix_ensaios_coleta_id'))

    op.drop_table('ensaios')
