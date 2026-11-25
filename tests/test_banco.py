"""Banco: migrations batem com o ORM, zerar mantém usuários, versão anterior é recusada com orientação."""
import sqlite3

import pytest

from fiep import db, usuarios
from fiep.orm import Usuario


def test_migrations_sobem_descem_e_batem_com_o_orm(tmp_path):
    from pathlib import Path

    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext

    import fiep
    from fiep.orm import Base, criar_engine, migrar
    caminho = tmp_path / "m.db"
    migrar(caminho)
    with criar_engine(caminho).connect() as con:
        assert compare_metadata(MigrationContext.configure(con, opts={"compare_type": True}), Base.metadata) == []
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(fiep.__file__).parent / "migracoes"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{caminho}")
    command.downgrade(cfg, "base")
    restantes = sqlite3.connect(caminho).execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert {r[0] for r in restantes} <= {"alembic_version"}


def test_zerar_mantem_usuarios_e_guarda_copia(tmp_path):
    banco = tmp_path / "z.db"
    s = db.conectar(banco)
    usuarios.criar(s, "adm@fiep.org", "Adm", "senha-muito-boa-1", "admin")
    s.close()
    r = db.zerar(banco)
    assert r["usuarios_mantidos"] == 1 and r["backup"] and (tmp_path / "backup").exists()
    u = db.conectar(banco).query(Usuario).filter_by(email="adm@fiep.org").one()
    assert u.papel == "admin" and usuarios.confere_senha("senha-muito-boa-1", u.senha_hash)   # mesma senha


def test_banco_da_versao_anterior_pede_zerar_e_zerar_resolve(tmp_path):
    banco = tmp_path / "velho.db"
    s = db.conectar(banco)
    usuarios.criar(s, "adm@fiep.org", "Adm", "senha-muito-boa-1", "admin")
    s.close()
    con = sqlite3.connect(banco)
    con.execute("UPDATE alembic_version SET version_num = '0005'")
    con.execute("CREATE TABLE amostras (sample_id TEXT)")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="versão anterior.*fiep db zerar"):
        db.conectar(banco)
    assert db.zerar(banco)["usuarios_mantidos"] == 1
    assert db.conectar(banco).query(Usuario).count() == 1


def test_usuarios_senha_com_hash(tmp_path):
    s = db.conectar(tmp_path / "u.db")
    u = usuarios.criar(s, "Ana@Fiep.org", "Ana", "senha-boa-123", "admin")
    assert u.email == "ana@fiep.org" and u.senha_hash.startswith("$2")
    assert usuarios.confere_senha("senha-boa-123", u.senha_hash)
    with pytest.raises(ValueError, match="pelo menos"):
        usuarios.criar(s, "b@fiep.org", "B", "curta")
    with pytest.raises(ValueError, match="Já existe"):
        usuarios.criar(s, "ana@fiep.org", "Ana 2", "outra-senha-boa")


def test_arquivo_que_nao_e_do_projeto_nao_e_tocado(tmp_path):
    caminho = tmp_path / "outro.db"
    sqlite3.connect(caminho).execute("CREATE TABLE clientes (id INTEGER)").connection.commit()
    with pytest.raises(RuntimeError, match="não é um banco da plataforma"):
        db.conectar(caminho)
