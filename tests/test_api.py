"""Plataforma: login, permissões, coletas pelo navegador, amostras e previsão."""
import io
import json
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from fiep import db, usuarios  # noqa: E402
from fiep.config import load_config  # noqa: E402
from fiep.ingest import ingerir  # noqa: E402
from fiep.model import treinar  # noqa: E402

from .conftest import gerar_case  # noqa: E402

H = {"X-Requested-With": "fiep"}
SENHA = "senha-de-teste-1"
NOMES = {"carbon_clean": "limpo", "capture_probe": "sonda", "capture_probe_16S_rRNA": "rRNA"}


@pytest.fixture
def plataforma(pasta_case, tmp_path):
    from api.app import criar_app
    from api.config import Config
    cfg = load_config()
    cfg["modelo"]["candidatos"] = ["log_reg"]
    treinar(ingerir(pasta_case), cfg, tmp_path / "modelos")
    banco = tmp_path / "plat.db"
    s = db.conectar(banco)
    usuarios.criar(s, "admin@fiep.org", "Admin", SENHA, "admin")
    usuarios.criar(s, "leitor@fiep.org", "Leitor", SENHA, "leitor")
    s.close()
    app = criar_app(Config(db_url=str(banco), segredo="x" * 40, modelos=str(tmp_path / "modelos"),
                           armazenamento=tmp_path / "recebidos", cookie_seguro=False, sessao_horas=1,
                           dados_exemplo=False, config_pipeline=None))
    with TestClient(app) as c:
        yield c


def entrar(c, email="admin@fiep.org", senha=SENHA):
    r = c.post("/api/auth/login", json={"email": email, "senha": senha}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def arquivos_coleta(n_amostras=4, prefixo="EMP"):
    """Excel exportado do NOVA, uma pasta por amostra, como o navegador envia (webkitRelativePath)."""
    sinal, meta, _ = gerar_case(n_amostras=n_amostras, n_rep=2, seed=3)
    files, caminhos, rotulos = [], [], {}
    for mid, g in sinal.groupby("measurement_id"):
        m = meta.set_index("measurement_id").loc[mid]
        sid = f"{prefixo}-{m.sample_id}"
        df = pd.DataFrame({"Potential applied (V)": g["potential_V"].to_numpy(),
                           "WE(1).δ.Current (A)": g["current_uA"].to_numpy() * 1e-6})
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        nome = f"DPV_{NOMES[m.sensor_state]}_E{m.replicate_id}.xlsx"
        files.append(("arquivos", (nome, buf.getvalue(), "application/octet-stream")))
        caminhos.append(f"{sid}/{nome}")
        rotulos[sid] = int(m.contamination_status)
    amostras = [{"sample_id": k, "contamination_status": v, "sample_log10_mean_cfu_ml": 5.0 if v else None}
                for k, v in rotulos.items()]
    return files, caminhos, amostras


def test_sem_login_nada_feito(plataforma):
    assert plataforma.get("/api/saude").status_code == 200            # pública, só o status
    assert plataforma.get("/api/painel").status_code == 401
    assert plataforma.get("/api/amostras").status_code == 401


def test_login_exige_cabecalho_csrf_e_cookie_protegido(plataforma):
    r = plataforma.post("/api/auth/login", json={"email": "admin@fiep.org", "senha": SENHA})
    assert r.status_code == 403
    r = plataforma.post("/api/auth/login", json={"email": "admin@fiep.org", "senha": SENHA}, headers=H)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and SENHA not in r.text
    assert plataforma.get("/api/auth/eu").json()["papel"] == "admin"
    plataforma.post("/api/auth/sair", headers=H)
    assert plataforma.get("/api/auth/eu").status_code == 401


def test_senha_errada_e_bloqueio(plataforma):
    for _ in range(5):
        r = plataforma.post("/api/auth/login", json={"email": "admin@fiep.org", "senha": "errada-123456"}, headers=H)
        assert r.status_code == 401 and r.json()["detail"] == "E-mail ou senha incorretos."
    r = plataforma.post("/api/auth/login", json={"email": "admin@fiep.org", "senha": SENHA}, headers=H)
    assert r.status_code == 429
    r = plataforma.post("/api/auth/login", json={"email": "ninguem@fiep.org", "senha": SENHA}, headers=H)
    assert r.status_code in (401, 429)


def test_papeis(plataforma):
    entrar(plataforma, "leitor@fiep.org")
    assert plataforma.get("/api/amostras").status_code == 200
    assert plataforma.post("/api/empresas", json={"nome": "X"}, headers=H).status_code == 403
    assert plataforma.get("/api/usuarios").status_code == 403
    files, caminhos, _ = arquivos_coleta(1)
    assert plataforma.post("/api/coletas", files=files, data={"caminhos": caminhos}, headers=H).status_code == 403


def test_admin_gerencia_usuarios_e_sessoes_caem(plataforma):
    entrar(plataforma)
    r = plataforma.post("/api/usuarios", json={"email": "col@fiep.org", "nome": "Col", "senha": "curta"}, headers=H)
    assert r.status_code == 400
    r = plataforma.post("/api/usuarios", json={"email": "col@fiep.org", "nome": "Col", "senha": SENHA,
                                               "papel": "colaborador"}, headers=H)
    uid = r.json()["id"]
    outro = TestClient(plataforma.app)
    entrar(outro, "col@fiep.org")
    assert outro.get("/api/auth/eu").status_code == 200
    plataforma.patch(f"/api/usuarios/{uid}", json={"ativo": False}, headers=H)
    assert outro.get("/api/auth/eu").status_code == 401            # desativado: sessão cai na hora
    me = plataforma.get("/api/auth/eu").json()["id"]
    r = plataforma.patch(f"/api/usuarios/{me}", json={"papel": "leitor"}, headers=H)
    assert r.status_code == 400                                     # não fica sem admin


def test_coleta_pelo_navegador_ate_a_previsao(plataforma):
    entrar(plataforma)
    emp = plataforma.post("/api/empresas", json={"nome": "Laticínio A", "cidade": "Curitiba"}, headers=H).json()
    files, caminhos, amostras = arquivos_coleta(4)
    r = plataforma.post("/api/coletas", files=files, headers=H, data={
        "caminhos": caminhos, "empresa_id": emp["id"], "descricao": "Visita 1", "data_coleta": "2026-11-03",
        "amostras": json.dumps(amostras)})
    assert r.status_code == 201, r.text
    col = r.json()
    assert col["n_amostras"] == 4 and col["amostras_sem_rotulo"] == 0 and col["importacao"]["medicoes"] == 24
    lista = plataforma.get(f"/api/amostras?coleta_id={col['id']}").json()
    assert lista["total"] == 4 and all(i["n_completas"] == 2 for i in lista["itens"])
    sid = lista["itens"][1]["sample_id"]
    d = plataforma.get(f"/api/amostras/{sid}").json()
    assert d["empresa"] == "Laticínio A" and len(d["medicoes"]) == 6
    cur = plataforma.get(f"/api/amostras/{sid}/curvas").json()
    assert len(cur) == 6 and len(cur[0]["potential_v"]) == len(cur[0]["current_ua"]) > 50
    r = plataforma.patch(f"/api/amostras/{sid}", json={"contamination_status": 1, "conjunto": "teste"}, headers=H)
    assert r.json()["conjunto"] == "teste" and r.json()["atualizado_por"] == "Admin"
    p = plataforma.post(f"/api/amostras/{sid}/prever", headers=H).json()
    assert p["amostra"]["resultado"] in ("CONTAMINADA", "NÃO CONTAMINADA") and p["amostra"]["replicas_avaliadas"] == 2
    assert plataforma.get(f"/api/amostras/{sid}").json()["previsoes"]
    painel = plataforma.get("/api/painel").json()
    assert painel["amostras"] == 4 and painel["coletas_recentes"][0]["empresa"] == "Laticínio A"
    # mesmo código de amostra em outra coleta: recusado, nada é gravado
    r = plataforma.post("/api/coletas", files=files, data={"caminhos": caminhos}, headers=H)
    assert r.status_code == 409 and len(plataforma.get("/api/coletas").json()) == 1
    assert plataforma.delete(f"/api/coletas/{col['id']}", headers=H).json()["ok"]
    assert plataforma.get("/api/amostras").json()["total"] == 0


def test_coleta_sem_voltamograma_e_caminho_malicioso(plataforma):
    entrar(plataforma)
    r = plataforma.post("/api/coletas", files=[("arquivos", ("notas.txt", b"oi", "text/plain"))], headers=H)
    assert r.status_code == 400 and plataforma.get("/api/coletas").json() == []
    files, _, _ = arquivos_coleta(1)
    r = plataforma.post("/api/coletas", files=files[:1], data={"caminhos": ["../../fora/x.xlsx"]}, headers=H)
    assert r.status_code in (201, 400)
    assert not (Path(plataforma.app.state.config.armazenamento).parent / "fora").exists()


def test_previsao_avulsa(plataforma):
    entrar(plataforma)
    files, caminhos, _ = arquivos_coleta(2, prefixo="NOVA")
    r = plataforma.post("/api/prever", files=files, data={"caminhos": caminhos}, headers=H).json()
    assert {a["sample_id"] for a in r["amostras"]} == {"NOVA-S000", "NOVA-S001"}
    assert plataforma.get("/api/amostras").json()["total"] == 0        # previsão avulsa não grava amostras
