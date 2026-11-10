import datetime as dt

import numpy as np
import pytest

from fiep import db, genossensor as g
from fiep.orm import Ensaio


@pytest.mark.parametrize("texto, esperado", [
    ("DPV SPCE H2SO4 Oligo 4N Branco", dict(tipo="branco", concentracao=0.0, elemento_captura="Oligo 4N")),
    ("DPV SPCE H2SO4 Oligo 4N 0,5 ng-mL", dict(tipo="alvo", concentracao=0.5, alvo="RNA")),
    ("DPV SPCE H2SO4 Oligo 4N RNA 155 ng-mL", dict(tipo="alvo", concentracao=155.0, tecnica="DPV",
                                                   tipo_eletrodo="SPCE", tratamento="H2SO4")),
    ("DPV SPCE Oligo 4N RNA 500 pg/mL", dict(tipo="alvo", concentracao=0.5)),
    ("DPV SPCE Oligo 4N controle negativo", dict(tipo="negativo", concentracao=0.0)),
])
def test_le_o_nome_do_procedimento(texto, esperado):
    r = g.ler_procedimento(texto)
    for k, v in esperado.items():
        assert r[k] == v, k


def test_eletrodo_vem_do_nome_do_arquivo():
    assert g.eletrodo_do_nome("dpv-rna-15-E1.nox") == "E1"
    assert g.eletrodo_do_nome("DPV_E12_branco.nox") == "E12"
    assert g.eletrodo_do_nome("dpv-rna-15.nox") is None


def _ensaio(eletrodo, tipo, conc, altura, minuto, **kw):
    return Ensaio(eletrodo_id=eletrodo, elemento_captura="Oligo 4N", tipo=tipo, concentracao=conc,
                  alvo="RNA" if tipo == "alvo" else None, altura_ua=altura, i_pico_ua=altura + 6,
                  e_pico_v=0.18, largura_v=0.1, area_uav=2.0, medido_em=dt.datetime(2025, 7, 31, 17, minuto), **kw)


def _base(tmp_path, n_eletrodos=4, seed=0):
    rng = np.random.default_rng(seed)
    s = db.conectar(tmp_path / "g.db", dados_exemplo=False)
    for k in range(n_eletrodos):
        el = f"E{k + 1}"
        s.add(_ensaio(el, "branco", 0, 7 + rng.normal(0, 0.2), 0))
        for j, c in enumerate([0.5, 5, 50]):
            s.add(_ensaio(el, "alvo", c, 7 * (1 - 0.1 * (np.log10(c) + 1.5)) + rng.normal(0, 0.1), 10 + j))
    s.flush()
    g.ligar_brancos(s)
    s.commit()
    return s


def test_alvo_liga_ao_branco_do_mesmo_eletrodo_e_sinal_relativo(tmp_path):
    s = _base(tmp_path)
    t = g.tabela(s)
    alvos = t[t["tipo"] == "alvo"]
    brancos = t[t["tipo"] == "branco"].set_index("id")
    assert alvos["branco_id"].notna().all()
    assert (brancos.loc[alvos["branco_id"], "eletrodo_id"].to_numpy() == alvos["eletrodo_id"].to_numpy()).all()
    assert (alvos["abaixo_do_branco"] == True).all()  # noqa: E712
    assert (alvos["sinal_rel_pct"] > 0).all()


def test_banco_recusa_branco_com_concentracao(tmp_path):
    from sqlalchemy.exc import IntegrityError
    s = db.conectar(tmp_path / "g.db", dados_exemplo=False)
    s.add(_ensaio("E1", "branco", 5.0, 7, 0))
    with pytest.raises(IntegrityError):
        s.commit()


def test_treinar_avisa_quando_falta_dado_e_roda_quando_ha(tmp_path):
    s = _base(tmp_path, n_eletrodos=1)
    r = g.treinar(g.tabela(s))
    assert r["status"] == "dados insuficientes" and r["nao_contaminado"] == 1
    s2 = _base(tmp_path / "b", n_eletrodos=4)
    r = g.treinar(g.tabela(s2))
    assert r["status"] == "ok" and r["validacao"] == "deixa um eletrodo de fora"
    assert 0 <= r["balanced_accuracy"] <= 1
    cal = r["calibracao"]
    assert cal["n"] == 12 and cal["inclinacao_pct_por_decada"] > 5 and cal["lod_ng_ml"] is not None


@pytest.mark.parametrize("nome, esperado", [
    ("dpv-bare-E1.nox", dict(tipo="bare", concentracao=0.0, eletrodo_id="E1", tecnica="DPV")),
    ("dpv-tratado-E3.nox", dict(tipo="tratado", concentracao=0.0, eletrodo_id="E3")),
    ("dpv-branco-E12.nox", dict(tipo="branco", concentracao=0.0, eletrodo_id="E12")),
    ("dpv-RNA-0,1-E2.nox", dict(tipo="alvo", concentracao=0.1, alvo="RNA", eletrodo_id="E2")),
    ("dpv-RNA-100,0-E2.nox", dict(tipo="alvo", concentracao=100.0)),
    ("dpv-negativo-E4.nox", dict(tipo="negativo", concentracao=0.0)),
])
def test_le_o_padrao_de_nome_da_equipe(nome, esperado):
    r = g.ler_nome(nome)
    for k, v in esperado.items():
        assert r[k] == v, k


def test_nome_fora_do_padrao_nao_inventa_nada():
    assert g.ler_nome("medida qualquer.nox") == {}


def test_bare_e_tratado_entram_sem_elemento_e_nao_ligam_ao_branco(tmp_path):
    s = db.conectar(tmp_path / "g.db", dados_exemplo=False)
    s.add(Ensaio(eletrodo_id="E1", tipo="bare", concentracao=0, altura_ua=3.0))
    s.add(Ensaio(eletrodo_id="E1", tipo="tratado", concentracao=0, altura_ua=5.0))
    s.add(_ensaio("E1", "branco", 0, 7, 0))
    s.add(_ensaio("E1", "alvo", 1.0, 5, 5))
    s.flush()
    assert g.ligar_brancos(s) == 1
    s.commit()
    t = g.tabela(s).set_index("tipo")
    assert t.loc["bare", "branco_id"] != t.loc["bare", "branco_id"]          # NaN
    assert t.loc["alvo", "altura_tratado_ua"] == 5.0 and t.loc["alvo", "altura_bare_ua"] == 3.0
    assert g.rotular(t.reset_index()).isna().sum() == 2                       # bare e tratado fora do treino
