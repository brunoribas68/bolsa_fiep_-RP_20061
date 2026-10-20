import os
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from fiep.config import load_config  # noqa: E402
from fiep.ingest import ingerir  # noqa: E402
from fiep.model import treinar  # noqa: E402

from .conftest import gerar_case  # noqa: E402


@pytest.fixture
def cliente(pasta_case, tmp_path, monkeypatch):
    cfg = load_config()
    cfg["modelo"]["candidatos"] = ["log_reg"]
    treinar(ingerir(pasta_case), cfg, tmp_path / "modelos")
    monkeypatch.setenv("FIEP_MODELOS", str(tmp_path / "modelos"))
    monkeypatch.setenv("FIEP_DB", str(tmp_path / "api.db"))
    import api.app as app_mod
    app_mod._estado.update({"pacote": None, "erro": None, "pasta": None})
    return TestClient(app_mod.app)


def test_pagina_e_saude(cliente):
    assert "Análise de voltamogramas" in cliente.get("/").text
    s = cliente.get("/api/saude").json()
    assert s["status"] == "ok" and s["modelo"]
    m = cliente.get("/api/modelo").json()
    assert 0 < m["limiar"] < 1


def test_prever_com_tabelas_e_grava_no_banco(cliente, tmp_path):
    sinal, meta, _ = gerar_case(n_amostras=3, seed=11)
    meta = meta.assign(contamination_status="")
    arquivos = [("arquivos", ("sinal.csv", sinal.to_csv(index=False).encode(), "text/csv")),
                ("arquivos", ("meta.csv", meta.to_csv(index=False).encode(), "text/csv"))]
    r = cliente.post("/api/prever", files=arquivos)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["resultados"]) == 6 and set(d["resumo"]) <= {"CONTAMINADA", "NÃO CONTAMINADA"}
    from fiep import db
    con = db.conectar(tmp_path / "api.db")
    assert con.execute("SELECT COUNT(*) FROM predicoes").fetchone()[0] == 6


def test_recusa_arquivo_invalido(cliente):
    r = cliente.post("/api/prever", files=[("arquivos", ("x.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400 and "não aceito" in r.json()["detail"]


def test_sem_modelo_responde_503(tmp_path, monkeypatch):
    monkeypatch.setenv("FIEP_MODELOS", str(tmp_path / "vazio"))
    import api.app as app_mod
    app_mod._estado.update({"pacote": None, "erro": None, "pasta": None})
    c = TestClient(app_mod.app)
    assert c.get("/api/saude").json()["status"] == "sem_modelo"
    assert c.get("/api/modelo").status_code == 503


PASTA = os.environ.get("FIEP_NOX_DIR")


@pytest.mark.skipif(not PASTA, reason="defina FIEP_NOX_DIR com .nox reais para rodar")
def test_nox_reais_planilha_e_previsao(cliente):
    noxs = sorted(Path(PASTA).glob("DPV*.nox"))[:3]
    files = [("arquivos", (n.name, n.read_bytes(), "application/octet-stream")) for n in noxs]
    r = cliente.post("/api/planilha", files=files)
    assert r.status_code == 200 and "arquivo" in r.text.splitlines()[0]
    r = cliente.post("/api/prever", files=files)          # sem planilha: amostra e estágio deduzidos
    assert r.status_code == 200
    res = r.json()["resultados"]
    assert {x["sample_id"] for x in res} == {"envio"}
    assert any("faltam os estágios" in (x["motivo"] or "") for x in res)
