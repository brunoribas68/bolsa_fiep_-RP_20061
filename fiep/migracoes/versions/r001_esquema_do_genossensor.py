"""esquema do genossensor: usuários, empresas, coletas, ensaios (branco/RNA), modelos e previsões

Substitui as migrations da versão com o case de exemplo (0001–0005). Um banco daquela versão é
recusado com a orientação de rodar `fiep db zerar`.

Revision ID: r001
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = 'r001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('empresas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=160), nullable=False),
    sa.Column('cidade', sa.String(length=120), nullable=True),
    sa.Column('segmento', sa.String(length=120), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_empresas')),
    sa.UniqueConstraint('nome', name=op.f('uq_empresas_nome'))
    )
    op.create_table('modelos',
    sa.Column('id', sa.String(length=40), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.Column('algoritmo', sa.String(length=60), nullable=False),
    sa.Column('representacao', sa.String(length=60), nullable=False),
    sa.Column('balanced_accuracy', sa.Float(), nullable=True),
    sa.Column('referencia', sa.String(length=40), nullable=True),
    sa.Column('n_ensaios', sa.Integer(), nullable=True),
    sa.Column('caminho', sa.String(length=500), nullable=True),
    sa.Column('cartao', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_modelos'))
    )
    op.create_table('usuarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('senha_hash', sa.String(length=100), nullable=False),
    sa.Column('papel', sa.String(length=20), nullable=False),
    sa.Column('instituicao', sa.String(length=120), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('versao_sessao', sa.Integer(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.Column('ultimo_login', sa.DateTime(), nullable=True),
    sa.CheckConstraint("papel IN ('admin', 'colaborador', 'leitor')", name=op.f('ck_usuarios_papel')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usuarios'))
    )
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usuarios_email'), ['email'], unique=True)

    op.create_table('coletas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=True),
    sa.Column('descricao', sa.String(length=300), nullable=True),
    sa.Column('data_coleta', sa.Date(), nullable=True),
    sa.Column('origem', sa.String(length=300), nullable=True),
    sa.Column('n_ensaios', sa.Integer(), nullable=False),
    sa.Column('avisos', sa.JSON(), nullable=True),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['criado_por_id'], ['usuarios.id'], name=op.f('fk_coletas_criado_por_id_usuarios')),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name=op.f('fk_coletas_empresa_id_empresas')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coletas'))
    )
    with op.batch_alter_table('coletas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_coletas_empresa_id'), ['empresa_id'], unique=False)

    op.create_table('predicoes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('modelo_id', sa.String(length=40), nullable=False),
    sa.Column('previsto_em', sa.DateTime(), nullable=False),
    sa.Column('arquivo', sa.String(length=300), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('eletrodo_id', sa.String(length=60), nullable=True),
    sa.Column('resultado', sa.String(length=30), nullable=False),
    sa.Column('prob_contaminado', sa.Float(), nullable=True),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('tipo_informado', sa.String(length=10), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['modelo_id'], ['modelos.id'], name=op.f('fk_predicoes_modelo_id_modelos')),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_predicoes_usuario_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_predicoes'))
    )
    with op.batch_alter_table('predicoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_predicoes_modelo_id'), ['modelo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_predicoes_sha256'), ['sha256'], unique=False)

    op.create_table('ensaios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=True),
    sa.Column('coleta_id', sa.Integer(), nullable=True),
    sa.Column('eletrodo_id', sa.String(length=60), nullable=False),
    sa.Column('canal', sa.String(length=60), nullable=True),
    sa.Column('elemento_captura', sa.String(length=120), nullable=True),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('bacteria', sa.String(length=120), nullable=True),
    sa.Column('concentracao', sa.Float(), nullable=False),
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
    sa.Column('potential_v', sa.JSON(), nullable=False),
    sa.Column('current_ua', sa.JSON(), nullable=False),
    sa.Column('qc_flag', sa.String(length=10), nullable=True),
    sa.Column('arquivo', sa.String(length=300), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.CheckConstraint("qc_flag IS NULL OR qc_flag IN ('PASS', 'FAIL')", name=op.f('ck_ensaios_qc_flag')),
    sa.CheckConstraint("tipo = 'rna' OR concentracao = 0", name=op.f('ck_ensaios_branco_sem_rna')),
    sa.CheckConstraint("tipo IN ('branco', 'rna')", name=op.f('ck_ensaios_tipo')),
    sa.CheckConstraint('concentracao >= 0', name=op.f('ck_ensaios_concentracao')),
    sa.ForeignKeyConstraint(['branco_id'], ['ensaios.id'], name=op.f('fk_ensaios_branco_id_ensaios'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['coleta_id'], ['coletas.id'], name=op.f('fk_ensaios_coleta_id_coletas'), ondelete='CASCADE'),
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
    with op.batch_alter_table('predicoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_predicoes_sha256'))
        batch_op.drop_index(batch_op.f('ix_predicoes_modelo_id'))

    op.drop_table('predicoes')
    with op.batch_alter_table('coletas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_coletas_empresa_id'))

    op.drop_table('coletas')
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usuarios_email'))

    op.drop_table('usuarios')
    op.drop_table('modelos')
    op.drop_table('empresas')
