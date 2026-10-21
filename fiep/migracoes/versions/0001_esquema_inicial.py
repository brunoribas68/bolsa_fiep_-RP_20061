"""esquema inicial: usuários, empresas, coletas, arquivos, amostras, medições, curvas, QC, modelos, previsões

Revision ID: 0001
Revises: 
Create Date: 2026-10-21 10:13:28.214179
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
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
    sa.Column('criado_em', sa.String(length=40), nullable=True),
    sa.Column('algoritmo', sa.String(length=160), nullable=True),
    sa.Column('versao_pipeline', sa.String(length=40), nullable=True),
    sa.Column('commit_codigo', sa.String(length=60), nullable=True),
    sa.Column('limiar', sa.Float(), nullable=True),
    sa.Column('balanced_accuracy', sa.Float(), nullable=True),
    sa.Column('sensibilidade', sa.Float(), nullable=True),
    sa.Column('especificidade', sa.Float(), nullable=True),
    sa.Column('roc_auc', sa.Float(), nullable=True),
    sa.Column('n_amostras', sa.Integer(), nullable=True),
    sa.Column('impressao_dados', sa.String(length=40), nullable=True),
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
    sa.Column('conjunto', sa.String(length=20), nullable=True),
    sa.Column('origem', sa.String(length=300), nullable=True),
    sa.Column('versao_pipeline', sa.String(length=40), nullable=True),
    sa.Column('n_medicoes', sa.Integer(), nullable=False),
    sa.Column('n_amostras', sa.Integer(), nullable=False),
    sa.Column('avisos', sa.JSON(), nullable=True),
    sa.Column('criado_por_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.CheckConstraint("conjunto IS NULL OR conjunto IN ('treino', 'validacao', 'teste')", name=op.f('ck_coletas_conjunto')),
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
    sa.Column('sample_id', sa.String(length=120), nullable=True),
    sa.Column('replicate_id', sa.String(length=40), nullable=True),
    sa.Column('measurement_id', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=60), nullable=True),
    sa.Column('resultado', sa.String(length=30), nullable=True),
    sa.Column('prob_contaminada', sa.Float(), nullable=True),
    sa.Column('confianca', sa.Float(), nullable=True),
    sa.Column('log10_ufc_ml_estimado', sa.Float(), nullable=True),
    sa.Column('nivel_contaminacao', sa.String(length=40), nullable=True),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('rotulo_informado', sa.Integer(), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['modelo_id'], ['modelos.id'], name=op.f('fk_predicoes_modelo_id_modelos')),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_predicoes_usuario_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_predicoes'))
    )
    with op.batch_alter_table('predicoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_predicoes_modelo_id'), ['modelo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_predicoes_sample_id'), ['sample_id'], unique=False)

    op.create_table('amostras',
    sa.Column('sample_id', sa.String(length=120), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=True),
    sa.Column('coleta_id', sa.Integer(), nullable=True),
    sa.Column('target_bacterium', sa.String(length=120), nullable=True),
    sa.Column('contamination_status', sa.Integer(), nullable=True),
    sa.Column('sample_log10_mean_cfu_ml', sa.Float(), nullable=True),
    sa.Column('surface_type', sa.String(length=120), nullable=True),
    sa.Column('sensor_lot', sa.String(length=60), nullable=True),
    sa.Column('conjunto', sa.String(length=20), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('extras', sa.JSON(), nullable=True),
    sa.Column('atualizado_em', sa.DateTime(), nullable=False),
    sa.Column('atualizado_por_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("conjunto IS NULL OR conjunto IN ('treino', 'validacao', 'teste')", name=op.f('ck_amostras_conjunto')),
    sa.CheckConstraint('contamination_status IS NULL OR contamination_status IN (0, 1)', name=op.f('ck_amostras_rotulo')),
    sa.ForeignKeyConstraint(['atualizado_por_id'], ['usuarios.id'], name=op.f('fk_amostras_atualizado_por_id_usuarios')),
    sa.ForeignKeyConstraint(['coleta_id'], ['coletas.id'], name=op.f('fk_amostras_coleta_id_coletas'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name=op.f('fk_amostras_empresa_id_empresas')),
    sa.PrimaryKeyConstraint('sample_id', name=op.f('pk_amostras'))
    )
    with op.batch_alter_table('amostras', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_amostras_coleta_id'), ['coleta_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_amostras_empresa_id'), ['empresa_id'], unique=False)

    op.create_table('arquivos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('arquivo', sa.String(length=300), nullable=False),
    sa.Column('papel', sa.String(length=40), nullable=False),
    sa.Column('tamanho_bytes', sa.Integer(), nullable=True),
    sa.Column('n_linhas', sa.Integer(), nullable=True),
    sa.Column('caminho', sa.String(length=500), nullable=True),
    sa.Column('coleta_id', sa.Integer(), nullable=True),
    sa.Column('importado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['coleta_id'], ['coletas.id'], name=op.f('fk_arquivos_coleta_id_coletas'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_arquivos'))
    )
    with op.batch_alter_table('arquivos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_arquivos_coleta_id'), ['coleta_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_arquivos_sha256'), ['sha256'], unique=True)

    op.create_table('medicoes',
    sa.Column('measurement_id', sa.String(length=200), nullable=False),
    sa.Column('sample_id', sa.String(length=120), nullable=True),
    sa.Column('replicate_id', sa.String(length=40), nullable=True),
    sa.Column('sensor_state', sa.String(length=60), nullable=True),
    sa.Column('tecnica', sa.String(length=20), nullable=True),
    sa.Column('fonte', sa.String(length=20), nullable=True),
    sa.Column('arquivo_origem', sa.String(length=300), nullable=True),
    sa.Column('contamination_status', sa.Integer(), nullable=True),
    sa.Column('qc_flag', sa.String(length=20), nullable=True),
    sa.Column('sensor_id', sa.String(length=60), nullable=True),
    sa.Column('sensor_lot', sa.String(length=60), nullable=True),
    sa.Column('experimental_batch', sa.String(length=60), nullable=True),
    sa.Column('surface_type', sa.String(length=120), nullable=True),
    sa.Column('operator_id', sa.String(length=60), nullable=True),
    sa.Column('measurement_date', sa.String(length=30), nullable=True),
    sa.Column('extras', sa.JSON(), nullable=True),
    sa.Column('coleta_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['coleta_id'], ['coletas.id'], name=op.f('fk_medicoes_coleta_id_coletas'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sample_id'], ['amostras.sample_id'], name=op.f('fk_medicoes_sample_id_amostras'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('measurement_id', name=op.f('pk_medicoes'))
    )
    with op.batch_alter_table('medicoes', schema=None) as batch_op:
        batch_op.create_index('ix_medicoes_amostra_replica', ['sample_id', 'replicate_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_medicoes_coleta_id'), ['coleta_id'], unique=False)

    op.create_table('plaqueamentos',
    sa.Column('sample_id', sa.String(length=120), nullable=False),
    sa.Column('plating_replicate_id', sa.Integer(), nullable=False),
    sa.Column('colony_count', sa.Float(), nullable=True),
    sa.Column('dilution_exponent', sa.Float(), nullable=True),
    sa.Column('plated_volume_ml', sa.Float(), nullable=True),
    sa.Column('plating_qualifier', sa.String(length=40), nullable=True),
    sa.Column('calculated_cfu_ml', sa.Float(), nullable=True),
    sa.Column('log10_cfu_ml', sa.Float(), nullable=True),
    sa.Column('arquivo_origem', sa.String(length=300), nullable=True),
    sa.Column('extras', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['sample_id'], ['amostras.sample_id'], name=op.f('fk_plaqueamentos_sample_id_amostras'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('sample_id', 'plating_replicate_id', name=op.f('pk_plaqueamentos'))
    )
    op.create_table('curvas',
    sa.Column('measurement_id', sa.String(length=200), nullable=False),
    sa.Column('n_pontos', sa.Integer(), nullable=False),
    sa.Column('potential_v', sa.JSON(), nullable=False),
    sa.Column('current_ua', sa.JSON(), nullable=False),
    sa.Column('scan_index', sa.JSON(), nullable=True),
    sa.Column('e_medido_v', sa.JSON(), nullable=True),
    sa.Column('i_bruta_ua', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['measurement_id'], ['medicoes.measurement_id'], name=op.f('fk_curvas_measurement_id_medicoes'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('measurement_id', name=op.f('pk_curvas'))
    )
    op.create_table('qc',
    sa.Column('measurement_id', sa.String(length=200), nullable=False),
    sa.Column('versao_pipeline', sa.String(length=40), nullable=False),
    sa.Column('avaliado_em', sa.DateTime(), nullable=False),
    sa.Column('qc_auto', sa.String(length=20), nullable=True),
    sa.Column('qc_planilha', sa.String(length=20), nullable=True),
    sa.Column('qc_final', sa.String(length=20), nullable=True),
    sa.Column('qc_motivos', sa.Text(), nullable=True),
    sa.Column('i_max_ua', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['measurement_id'], ['medicoes.measurement_id'], name=op.f('fk_qc_measurement_id_medicoes'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('measurement_id', 'versao_pipeline', name=op.f('pk_qc'))
    )


def downgrade() -> None:
    op.drop_table('qc')
    op.drop_table('curvas')
    op.drop_table('plaqueamentos')
    with op.batch_alter_table('medicoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_medicoes_coleta_id'))
        batch_op.drop_index('ix_medicoes_amostra_replica')

    op.drop_table('medicoes')
    with op.batch_alter_table('arquivos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_arquivos_sha256'))
        batch_op.drop_index(batch_op.f('ix_arquivos_coleta_id'))

    op.drop_table('arquivos')
    with op.batch_alter_table('amostras', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_amostras_empresa_id'))
        batch_op.drop_index(batch_op.f('ix_amostras_coleta_id'))

    op.drop_table('amostras')
    with op.batch_alter_table('predicoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_predicoes_sample_id'))
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
