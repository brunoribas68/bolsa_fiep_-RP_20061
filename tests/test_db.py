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
    return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def test_importar_e_reimportar_nao_duplica(pasta_case, banco):
    ds = ingerir(pasta_case)
    r1 = db.importar(banco, ds, "lote 1")
    assert r1["arquivos_novos"] == 3
    r2 = db.importar(banco, ds, "lote 1 de novo")
    assert r2["arquivos_novos"] == 0
    assert _contar(banco, "medicoes") == len(ds.medicoes)
    assert _contar(banco, "pontos") == len(ds.pontos)
    assert _contar(banco, "amostras") == ds.medicoes["sample_id"].nunique()
    assert _contar(banco, "importacoes") == 2


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
    v = pd.read_sql("SELECT * FROM v_predicoes", banco)
    assert (v["modelo_id"] == r["cartao"]["id"]).all()
    rep = pd.read_sql("SELECT * FROM v_replicatas", banco)
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
