"""Plataforma: login, permissões, coletas de .nox pelo navegador, ensaios, gráficos, modelos e previsão."""
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from fiep import db, usuarios  # noqa: E402

from .conftest import gerar_pasta  # noqa: E402

H = {"X-Requested-With": "fiep"}
SENHA = "senha-de-teste-1"


@pytest.fixture
def plataforma(tmp_path, nox_sintetico):
    from api.app import criar_app
    from api.config import Config
    banco = tmp_path / "plat.db"
    s = db.conectar(banco)
    usuarios.criar(s, "admin@fiep.org", "Admin", SENHA, "admin")
    usuarios.criar(s, "leitor@fiep.org", "Leitor", SENHA, "leitor")
    s.close()
    app = criar_app(Config(db_url=str(banco), segredo="x" * 40, modelos=str(tmp_path / "modelos"),
                           armazenamento=tmp_path / "recebidos", cookie_seguro=False, sessao_horas=1))
    with TestClient(app) as c:
        c.tmp = tmp_path
        yield c


def entrar(c, email="admin@fiep.org", senha=SENHA):
    r = c.post("/api/auth/login", json={"email": email, "senha": senha}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def arquivos_coleta(tmp, n_eletrodos=4, seed=0):
    """Os .nox como o navegador envia uma pasta (caminho relativo de cada arquivo)."""
    pasta = gerar_pasta(tmp / f"envio{seed}", n_eletrodos=n_eletrodos, seed=seed)
    files, caminhos = [], []
    for p in sorted(pasta.rglob("*.nox")):
        files.append(("arquivos", (p.name, p.read_bytes(), "application/octet-stream")))
        caminhos.append(p.relative_to(pasta).as_posix())
    return files, caminhos


def esperar(c, tid):
    for _ in range(240):
        t = c.get(f"/api/treinos/{tid}").json()
        if t["estado"] not in ("na fila", "rodando"):
            return t
        time.sleep(.5)
    raise AssertionError("treino não terminou")


def test_sem_login_nada_feito(plataforma):
    assert plataforma.get("/api/saude").status_code == 200            # pública, só o status
    assert plataforma.get("/api/painel").status_code == 401
    assert plataforma.get("/api/ensaios").status_code == 401


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
    assert plataforma.get("/api/ensaios").status_code == 200
    assert plataforma.post("/api/empresas", json={"nome": "X"}, headers=H).status_code == 403
    assert plataforma.get("/api/usuarios").status_code == 403
    files, caminhos = arquivos_coleta(plataforma.tmp, 1)
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


def test_coleta_pelo_navegador_ensaios_e_edicao(plataforma):
    entrar(plataforma)
    emp = plataforma.post("/api/empresas", json={"nome": "Laboratório A", "cidade": "Curitiba"}, headers=H).json()
    files, caminhos = arquivos_coleta(plataforma.tmp, 4)
    r = plataforma.post("/api/coletas", files=files, headers=H, data={
        "caminhos": caminhos, "empresa_id": emp["id"], "descricao": "Lote 1", "data_coleta": "2026-11-19"})
    assert r.status_code == 201, r.text
    col = r.json()
    assert col["n_ensaios"] == 16 and col["n_branco"] == 4 and col["n_rna"] == 12 and len(col["ensaios"]) == 16
    assert col["importacao"]["ligados_ao_branco"] == 12
    lista = plataforma.get(f"/api/ensaios?empresa_id={emp['id']}").json()
    assert len(lista["ensaios"]) == 16 and lista["calibracao"]["n"] == 12
    rna = next(e for e in lista["ensaios"] if e["tipo"] == "rna")
    d = plataforma.get(f"/api/ensaios/{rna['id']}").json()
    assert len(d["potential_v"]) == 179 and d["branco"]["arquivo"].startswith("dpv-branco")
    r = plataforma.patch(f"/api/ensaios/{rna['id']}", json={"qc_flag": "FAIL", "observacoes": "bolha"}, headers=H)
    assert r.json()["qc_flag"] == "FAIL"
    assert plataforma.patch(f"/api/ensaios/{rna['id']}", json={"concentracao": 0}, headers=H).status_code == 400
    r = plataforma.patch(f"/api/ensaios/{rna['id']}", json={"tipo": "branco"}, headers=H).json()
    assert r["concentracao"] == 0 and r["branco_id"] is None
    painel = plataforma.get("/api/painel").json()
    assert painel["branco"] == 5 and painel["rna"] == 11 and painel["coletas_recentes"][0]["empresa"] == "Laboratório A"
    assert plataforma.get("/api/empresas").json()[0]["n_ensaios"] == 16
    # o mesmo envio de novo: nada novo, nada gravado
    r = plataforma.post("/api/coletas", files=files, data={"caminhos": caminhos}, headers=H)
    assert r.status_code == 400 and "já estavam no banco" in r.json()["detail"]
    assert len(plataforma.get("/api/coletas").json()) == 1
    assert plataforma.delete(f"/api/coletas/{col['id']}", headers=H).json()["ok"]
    assert plataforma.get("/api/ensaios").json()["ensaios"] == []


def test_coleta_com_arquivo_na_pasta_errada_e_caminho_malicioso(plataforma):
    entrar(plataforma)
    r = plataforma.post("/api/coletas", files=[("arquivos", ("notas.txt", b"oi", "text/plain"))], headers=H)
    assert r.status_code == 400 and plataforma.get("/api/coletas").json() == []
    files, caminhos = arquivos_coleta(plataforma.tmp, 1)
    branco = caminhos.index("nao_contaminado/dpv-branco-E1.nox")
    caminhos[branco] = "contaminado/dpv-branco-E1.nox"
    r = plataforma.post("/api/coletas", files=files, data={"caminhos": caminhos}, headers=H).json()
    assert r["n_ensaios"] == 3 and any("está em contaminado/" in a for a in r["avisos"])
    files, _ = arquivos_coleta(plataforma.tmp, 1, seed=5)
    r = plataforma.post("/api/coletas", files=files[:1], data={"caminhos": ["../../fora/x.nox"]}, headers=H)
    assert r.status_code in (201, 400)
    assert not (Path(plataforma.app.state.config.armazenamento).parent / "fora").exists()


def test_treino_pela_plataforma_previsao_e_graficos(plataforma):
    entrar(plataforma)
    assert plataforma.get("/api/graficos").json()["curvas"] == []
    assert plataforma.get("/api/saude").json()["modelo"] is None
    files, caminhos = arquivos_coleta(plataforma.tmp, 12)
    assert plataforma.post("/api/coletas", files=files, data={"caminhos": caminhos}, headers=H).status_code == 201
    g = plataforma.get("/api/graficos").json()
    assert len(g["curvas"]) == 48 and len(g["curvas"][0]["e"]) == 179 and len(g["pontos"]) == 48
    cat = plataforma.get("/api/catalogo").json()
    assert {"log_reg", "mlp", "sisso"} <= {a["id"] for a in cat["algoritmos"]}
    assert {v["id"] for v in cat["variantes"]} == {"curva", "forma", "derivada", "pico"}
    r = plataforma.post("/api/treinos", json={"algoritmos": ["log_reg", "lda"], "variantes": ["curva"],
                                              "ativar": True}, headers=H)
    assert r.status_code == 202
    assert plataforma.post("/api/treinos", json={}, headers=H).status_code == 409       # um por vez
    t = esperar(plataforma, r.json()["id"])
    assert t["estado"] == "concluido", t
    lista = plataforma.get("/api/modelos").json()
    assert len(lista) == 1 and lista[0]["em_uso"] and lista[0]["referencia"] == "teste"
    d = plataforma.get(f"/api/modelos/{t['modelo']}").json()
    assert {x["algoritmo"] for x in d["placar"]} == {"log_reg", "lda"} and d["em_uso"]
    assert plataforma.get("/api/saude").json()["modelo"] == t["modelo"]
    novos, _ = arquivos_coleta(plataforma.tmp, 1, seed=7)
    p = plataforma.post("/api/prever", files=novos, data={"salvar": "true"}, headers=H).json()
    assert len(p["resultados"]) == 4 and sum(p["resumo"].values()) == 4
    assert {r["resultado"] for r in p["resultados"]} <= {"CONTAMINADO", "NÃO CONTAMINADO"}
    assert all(len(r["current_ua"]) == 179 for r in p["resultados"])
    assert len(plataforma.get("/api/ensaios").json()["ensaios"]) == 48       # previsão não entra na base
    assert plataforma.post("/api/treinos", json={"algoritmos": ["inexistente"]}, headers=H).status_code == 400
    entrar(plataforma, "leitor@fiep.org")
    assert plataforma.post("/api/treinos", json={}, headers=H).status_code == 403
