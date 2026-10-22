import numpy as np
import pandas as pd
import pytest

from fiep import db
from fiep.cli import main
from fiep.config import load_config
from fiep.ingest import ingerir
from fiep.model import treinar
from fiep.predict import prever
from fiep.qc import avaliar


@pytest.fixture
def banco(tmp_path):
    con = db.conectar(tmp_path / "fiep.db")
    yield con
    con.close()


def _contar(con, tabela):
    return int(db.sql(con, f"SELECT COUNT(*) FROM {tabela}").iloc[0, 0])


def test_importar_e_reimportar_nao_duplica(pasta_case, banco):
    ds = ingerir(pasta_case)
    r1 = db.importar(banco, ds, "lote 1")
    assert r1["arquivos_novos"] == 3
    r2 = db.importar(banco, ds, "lote 1 de novo")
    assert r2["arquivos_novos"] == 0
    assert _contar(banco, "medicoes") == len(ds.medicoes)
    assert int(db.sql(banco, "SELECT SUM(n_pontos) FROM curvas").iloc[0, 0]) == len(ds.pontos)
    assert _contar(banco, "amostras") == ds.medicoes["sample_id"].nunique()
    assert _contar(banco, "coletas") == 2


def test_carregar_devolve_os_mesmos_dados(pasta_case, banco):
    ds = ingerir(pasta_case)
    db.importar(banco, ds)
    volta = db.carregar(banco)
    assert len(volta.medicoes) == len(ds.medicoes)
    a = ds.pontos.sort_values(["measurement_id", "potential_v"])["current_ua"].to_numpy()
    b = volta.pontos.sort_values(["measurement_id", "potential_v"])["current_ua"].to_numpy()
    assert np.allclose(a, b)
    filtrado = db.carregar(banco, "sensor_state = ?", ("carbon_clean",))
    assert set(filtrado.medicoes["sensor_state"]) == {"carbon_clean"}


def test_treino_pelo_banco_igual_ao_dos_arquivos(pasta_case, banco, tmp_path):
    cfg = load_config()
    cfg["modelo"]["candidatos"] = ["log_reg"]
    ds = ingerir(pasta_case)
    db.importar(banco, ds)
    r_arq = treinar(ds, cfg, tmp_path / "m1")
    r_db = treinar(db.carregar(banco), cfg, tmp_path / "m2")
    assert r_arq["cartao"]["metricas_cv"]["balanced_accuracy"] == pytest.approx(
        r_db["cartao"]["metricas_cv"]["balanced_accuracy"])


def test_qc_modelo_e_predicoes_ficam_registrados(pasta_case, banco, tmp_path):
    cfg = load_config()
    cfg["modelo"]["candidatos"] = ["log_reg"]
    ds = ingerir(pasta_case)
    db.importar(banco, ds)
    assert db.gravar_qc(banco, avaliar(ds.medicoes, ds.pontos, cfg)) == len(ds.medicoes)
    r = treinar(ds, cfg, tmp_path / "m")
    db.registrar_modelo(banco, r["cartao"], r["pasta"])
    from fiep.model import carregar
    pacote = carregar(tmp_path / "m")
    res = prever(ds, pacote)
    assert db.gravar_predicoes(banco, res, pacote["cartao"]) == len(res)
    v = db.sql(banco, "SELECT * FROM v_predicoes")
    assert (v["modelo_id"] == r["cartao"]["id"]).all()
    rep = db.sql(banco, "SELECT * FROM v_replicatas")
    assert (rep["n_aprovadas"] == 3).all()


def test_exportar_excel_e_csv(pasta_case, banco, tmp_path):
    db.importar(banco, ingerir(pasta_case))
    arq = db.exportar(banco, tmp_path / "banco.xlsx")[0]
    abas = pd.read_excel(arq, sheet_name=None)
    assert {"amostras", "medicoes", "pontos", "v_replicatas"} <= set(abas)
    csvs = db.exportar(banco, tmp_path / "csv", "csv")
    assert any(p.name == "medicoes.csv" for p in csvs)


def test_cli_db(pasta_case, tmp_path, capsys):
    caminho = str(tmp_path / "cli.db")
    assert main(["db", "importar", "--entrada", str(pasta_case), "--db", caminho]) == 0
    assert main(["db", "sql", "SELECT COUNT(*) AS n FROM medicoes", "--db", caminho]) == 0
    assert "144" in capsys.readouterr().out
    assert main(["db", "sql", "--db", caminho]) == 1          # sem consulta: erro amigável


def test_migrations_sobem_descem_e_batem_com_o_orm(tmp_path):
    """O banco criado pelas migrations tem exatamente o que o modelo ORM declara."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from fiep.orm import Base, criar_engine, migrar
    caminho = tmp_path / "m.db"
    migrar(caminho, dados_exemplo=False)
    with criar_engine(caminho).connect() as con:
        diff = compare_metadata(MigrationContext.configure(con, opts={"compare_type": True}), Base.metadata)
    assert [d for d in diff if not (d[0] == "remove_table" and str(d[1].name).startswith("v_"))] == []
    from alembic import command
    from alembic.config import Config
    from pathlib import Path
    import fiep
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(fiep.__file__).parent / "migracoes"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{caminho}")
    command.downgrade(cfg, "base")
    import sqlite3
    restantes = sqlite3.connect(caminho).execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')").fetchall()
    assert {r[0] for r in restantes} <= {"alembic_version"}


def test_dados_de_exemplo_carregam_e_saem(tmp_path):
    s = db.conectar(tmp_path / "ex.db", dados_exemplo=True)
    assert _contar(s, "amostras") == 200 and _contar(s, "medicoes") == 1800
    assert len(db.carregar(s, "tecnica = 'DPV'").medicoes) == 1800
    assert db.remover_exemplo(s)
    assert _contar(s, "amostras") == 0 and _contar(s, "curvas") == 0
    assert db.carregar_exemplo(s)["amostras"] == 200


def test_usuarios_senha_com_hash(tmp_path):
    from fiep import usuarios
    s = db.conectar(tmp_path / "u.db")
    u = usuarios.criar(s, "Ana@Fiep.org", "Ana", "senha-boa-123", "admin")
    assert u.email == "ana@fiep.org" and u.senha_hash.startswith("$2")
    assert usuarios.confere_senha("senha-boa-123", u.senha_hash)
    assert not usuarios.confere_senha("errada-errada", u.senha_hash)
    with pytest.raises(ValueError, match="pelo menos"):
        usuarios.criar(s, "b@fiep.org", "B", "curta")
    with pytest.raises(ValueError, match="Já existe"):
        usuarios.criar(s, "ana@fiep.org", "Ana 2", "outra-senha-boa")


def test_banco_antigo_e_convertido_sem_perder_dados(tmp_path):
    """Banco criado pela versão anterior (sem migrations): vira backup e é convertido."""
    import json
    import sqlite3

    from fiep.legado import ESQUEMA_V1
    caminho = tmp_path / "fiep.db"
    con = sqlite3.connect(caminho)
    con.executescript(ESQUEMA_V1)
    con.execute("INSERT INTO meta_esquema VALUES (1, '2026-10-20')")
    con.execute("INSERT INTO importacoes (id, importado_em, origem) VALUES (1, '2026-10-20', 'dados')")
    con.execute("INSERT INTO arquivos VALUES ('abc', 'x.nox', 'nox', 10, 3, 1, '2026-10-20')")
    con.execute("INSERT INTO amostras VALUES ('A1', 'E. coli', 1, 5.5, 'L1', NULL, '2026-10-20')")
    for k, est in enumerate(["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"]):
        mid = f"A1_{k}"
        con.execute("INSERT INTO medicoes (measurement_id, sample_id, replicate_id, sensor_state, tecnica, fonte, "
                    "arquivo_origem, extras, importacao_id) VALUES (?, 'A1', 1, ?, 'DPV', 'nox', 'x.nox', ?, 1)",
                    (mid, est, json.dumps({"canal": "1"})))
        con.executemany("INSERT INTO pontos VALUES (?, 1, ?, ?, ?, NULL, NULL)",
                        [(mid, i, -0.2 + i * 0.01, float(i % 7)) for i in range(60)])
        con.execute("INSERT INTO qc VALUES (?, '0.1.0', '2026-10-20', 'PASS', NULL, 'PASS', '', 7.0)", (mid,))
    con.execute("INSERT INTO modelos (id, criado_em, algoritmo, cartao) VALUES ('m1', '2026', 'log_reg', ?)",
                (json.dumps({"id": "m1", "modelo": "log_reg", "limiar": 0.5}),))
    con.execute("INSERT INTO predicoes (modelo_id, previsto_em, sample_id, replicate_id, status, resultado) "
                "VALUES ('m1', '2026', 'A1', 1, 'avaliada', 'CONTAMINADA')")
    con.commit()
    con.close()

    s = db.conectar(caminho)                      # o que o `fiep usuario criar` faz
    assert len(list(tmp_path.glob("fiep.antigo-*.db"))) == 1
    assert _contar(s, "amostras") == 1 and _contar(s, "medicoes") == 3 and _contar(s, "predicoes") == 1
    ds = db.carregar(s)
    assert len(ds.pontos) == 180 and set(ds.medicoes["canal"]) == {"1"}
    assert db.sql(s, "SELECT n_aprovadas FROM v_replicatas").iloc[0, 0] == 3
    s.close()
    db.conectar(caminho).close()                  # segunda vez: já está no formato novo, nada muda
    assert len(list(tmp_path.glob("fiep.antigo-*.db"))) == 1


def test_arquivo_que_nao_e_do_projeto_nao_e_tocado(tmp_path):
    import sqlite3
    caminho = tmp_path / "outro.db"
    sqlite3.connect(caminho).execute("CREATE TABLE clientes (id INTEGER)").connection.commit()
    with pytest.raises(RuntimeError, match="não é um banco da plataforma"):
        db.conectar(caminho)


def test_experimento_pelo_banco_deixa_o_exemplo_de_fora(pasta_case, tmp_path, capsys):
    caminho = tmp_path / "e.db"
    s = db.conectar(caminho, dados_exemplo=True)
    db.importar(s, ingerir(pasta_case), empresa="Empresa real")
    s.close()
    assert main(["experimento", "--db", str(caminho), "--rapido", "--saida", str(tmp_path / "r"),
                 "--modelos", str(tmp_path / "m")]) == 0
    out = capsys.readouterr().out
    assert "Dados de exemplo deixados de fora" in out and "treino: 12 amostras" in out


def test_prever_sem_modelo_explica(tmp_path, capsys):
    assert main(["prever", "--entrada", str(tmp_path), "--modelo", str(tmp_path / "nada")]) == 1
    assert "rode `fiep experimento`" in capsys.readouterr().err
