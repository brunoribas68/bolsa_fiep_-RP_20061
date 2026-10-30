"""Banco: zerar e recriar."""
from fiep import db
def test_zerar_mantem_usuarios_e_guarda_copia(tmp_path):
    from fiep import usuarios
    from fiep.orm import Usuario
    banco = tmp_path / "z.db"
    s = db.conectar(banco, dados_exemplo=True)
    usuarios.criar(s, "adm@fiep.org", "Adm", "senha-muito-boa-1", "admin")
    assert int(db.sql(s, "SELECT COUNT(*) FROM amostras").iloc[0, 0]) > 0
    s.close()
    r = db.zerar(banco, manter_usuarios=True, dados_exemplo=False)
    assert r["usuarios_mantidos"] == 1 and r["backup"] and (tmp_path / "backup").exists()
    s = db.conectar(banco, dados_exemplo=False)
    assert int(db.sql(s, "SELECT COUNT(*) FROM amostras").iloc[0, 0]) == 0
    u = s.query(Usuario).filter_by(email="adm@fiep.org").one()
    assert u.papel == "admin" and usuarios.confere_senha("senha-muito-boa-1", u.senha_hash)   # mesma senha
