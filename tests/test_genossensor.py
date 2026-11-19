"""Base do genossensor: leitura dos nomes, pastas, importação, ligação ao branco e calibração."""
import numpy as np
import pytest

from fiep import db, genossensor as g

from .conftest import curva, escrever_nox


@pytest.mark.parametrize("texto, esperado", [
    ("DPV SPCE H2SO4 Oligo 4N Branco", dict(tipo="branco", concentracao=0.0, elemento_captura="Oligo 4N",
                                            tecnica="DPV", tipo_eletrodo="SPCE", tratamento="H2SO4")),
    ("DPV SPCE H2SO4 Oligo 4N RNA 1,5 ng-mL", dict(tipo="rna", concentracao=1.5)),
    ("DPV SPCE Oligo 4N RNA 500 pg/mL", dict(tipo="rna", concentracao=0.5)),
    ("DPV SPCE qualquer coisa", dict(tipo=None)),
])
def test_le_o_nome_do_procedimento(texto, esperado):
    r = g.ler_procedimento(texto)
    assert {k: r[k] for k in esperado} == esperado


@pytest.mark.parametrize("nome, esperado", [
    ("dpv-branco-E12.nox", dict(tipo="branco", concentracao=0.0, eletrodo_id="E12", tecnica="DPV")),
    ("dpv-RNA-0,1-E2.nox", dict(tipo="rna", concentracao=0.1, eletrodo_id="E2", conc_com_decimal=True)),
    ("dpv-RNA-100,0-E2.nox", dict(tipo="rna", concentracao=100.0)),
    ("dpv-rna-15-E1.nox", dict(tipo="rna", concentracao=15.0, conc_com_decimal=False)),   # nome antigo
    ("dpv-bare-E1.nox", dict(tipo="bare", eletrodo_id="E1")),
])
def test_le_o_padrao_de_nome_da_equipe(nome, esperado):
    r = g.ler_nome(nome)
    assert {k: r[k] for k in esperado} == esperado


def test_nome_fora_do_padrao_nao_inventa_nada():
    assert g.ler_nome("medida qualquer.nox") == {}


def test_pastas_e_conferencia(tmp_path):
    c, n = g.criar_pastas(tmp_path / "rna")
    assert c.name == "contaminado" and n.name == "nao_contaminado" and c.is_dir() and n.is_dir()
    raiz = tmp_path / "rna"
    assert g.pasta_do_arquivo(c / "x.nox", raiz) == "contaminado"
    assert g.pasta_do_arquivo(raiz / "Não Contaminado" / "lote2" / "x.nox", raiz) == "nao_contaminado"
    assert g.pasta_do_arquivo(raiz / "x.nox", raiz) is None
    assert g.conferir_pasta("contaminado", "rna") is None and g.conferir_pasta("nao_contaminado", "branco") is None
    assert g.conferir_pasta("contaminado", "branco") and g.conferir_pasta("nao_contaminado", "rna")
    assert g.conferir_pasta(None, "rna") is None


def test_importa_liga_ao_branco_e_nao_duplica(pasta_rna, tmp_path):
    s = db.conectar(tmp_path / "g.db")
    r = g.importar(s, pasta_rna, empresa="SENAI")
    assert r["lidos"] == r["gravados"] == 16 and r["ligados_ao_branco"] == 12 and r["avisos"] == []
    t = g.tabela(s)
    rna, branco = t[t.tipo == "rna"], t[t.tipo == "branco"].set_index("id")
    assert (branco.loc[rna["branco_id"], "eletrodo_id"].to_numpy() == rna["eletrodo_id"].to_numpy()).all()
    assert (rna["abaixo_do_branco"] == True).all() and (rna["queda_pct"] > 0).all()  # noqa: E712
    assert set(t["elemento_captura"]) == {"Oligo 4N"} and set(rna["concentracao"]) == {0.5, 5.0, 50.0}
    de_novo = g.importar(s, pasta_rna)
    assert de_novo["gravados"] == 0 and de_novo["ja_no_banco"] == 16 and de_novo["coleta_id"] is None


def test_o_que_nao_entra_fica_de_fora_com_o_motivo(tmp_path, nox_sintetico):
    rng = np.random.default_rng(1)
    p = tmp_path / "rna"
    escrever_nox(p / "contaminado" / "dpv-branco-E1.nox", "DPV Oligo 4N Branco", *curva(rng, False))   # pasta errada
    escrever_nox(p / "dpv-bare-E1.nox", "DPV SPCE bare", *curva(rng, False))                              # outra etapa
    escrever_nox(p / "dpv-RNA-1,0.nox", "DPV Oligo 4N RNA 1 ng-mL", *curva(rng, True))                   # sem eletrodo
    escrever_nox(p / "dpv-RNA-2,0-E1.nox", "DPV Oligo 4N RNA 2 ng-mL", *curva(rng, True))                # este entra
    s = db.conectar(tmp_path / "g.db")
    r = g.importar(s, p)
    assert r["gravados"] == 1 and r["nao_gravados"] == 3
    avisos = " | ".join(r["avisos"])
    assert "está em contaminado/" in avisos and "etapa 'bare'" in avisos and "sem o eletrodo" in avisos


def test_concentracao_do_nome_novo_e_do_procedimento_no_nome_antigo(tmp_path, nox_sintetico):
    rng = np.random.default_rng(2)
    p = tmp_path / "rna"
    escrever_nox(p / "dpv-rna-15-E1.nox", "DPV Oligo 4N RNA 1,5 ng-mL", *curva(rng, True))     # antigo: 1,5
    escrever_nox(p / "dpv-RNA-10,0-E2.nox", "DPV Oligo 4N RNA 5 ng-mL", *curva(rng, True))     # nome manda: 10
    r = {x["arquivo"]: x for x in g.ler_pasta(p)[0].to_dict("records")}
    assert r["dpv-rna-15-E1.nox"]["concentracao"] == 1.5
    assert r["dpv-RNA-10,0-E2.nox"]["concentracao"] == 10.0 and "≠ procedimento" in r["dpv-RNA-10,0-E2.nox"]["observacoes"]


def test_ensaios_csv_corrige_e_opcoes_preenchem(tmp_path, nox_sintetico):
    rng = np.random.default_rng(3)
    p = tmp_path / "rna"
    escrever_nox(p / "medida1.nox", "DPV SPCE Branco", *curva(rng, False))
    escrever_nox(p / "medida2.nox", "DPV SPCE RNA 3 ng-mL", *curva(rng, True))
    (p / "ensaios.csv").write_text("arquivo;eletrodo_id;qc_flag\nmedida1.nox;E7;\nmedida2.nox;E7;FAIL\n")
    s = db.conectar(tmp_path / "g.db")
    r = g.importar(s, p, elemento="Oligo 5N", bacteria="E. coli")
    assert r["gravados"] == 2
    t = g.tabela(s).set_index("arquivo")
    assert t.loc["medida2.nox", "branco_id"] == t.loc["medida1.nox", "id"]
    assert t.loc["medida2.nox", "qc_flag"] == "FAIL" and set(t["elemento_captura"]) == {"Oligo 5N"}
    assert set(t["bacteria"]) == {"E. coli"}


def test_banco_recusa_branco_com_concentracao(tmp_path):
    from sqlalchemy.exc import IntegrityError
    from fiep.orm import Ensaio
    s = db.conectar(tmp_path / "g.db")
    s.add(Ensaio(eletrodo_id="E1", tipo="branco", concentracao=5.0, potential_v=[], current_ua=[], sha256="x"))
    with pytest.raises(IntegrityError):
        s.commit()


def test_calibracao_e_limite_de_deteccao(pasta_rna, tmp_path):
    s = db.conectar(tmp_path / "g.db")
    g.importar(s, pasta_rna)
    cal = g.calibracao(g.tabela(s))
    assert cal["n"] == 12 and cal["inclinacao_pct_por_decada"] > 0 and cal["lod_ng_ml"] is not None
