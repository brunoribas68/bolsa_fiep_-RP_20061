"""Modelo pela curva: requisitos de dados, separação por eletrodo, registro e previsão."""
import numpy as np
import pytest

from fiep import db, genossensor as g, modelagem as m

from .conftest import E, curva, escrever_nox, gerar_pasta


def _base(tmp_path, n_eletrodos, seed=0):
    gerar_pasta(tmp_path / "rna", n_eletrodos=n_eletrodos, seed=seed)
    s = db.conectar(tmp_path / "m.db")
    g.importar(s, tmp_path / "rna")
    return s, g.tabela(s, incluir_curvas=True)


def test_representacoes_tem_o_mesmo_tamanho_e_nome_de_coluna():
    rng = np.random.default_rng(0)
    curvas = [curva(rng, False), curva(rng, True, 5)]
    grade = m.grade_comum(curvas)
    for v in m.VARIANTES:
        X = m.representar(curvas, v, grade)
        assert X.shape == (2, 6 if v == "pico" else m.N_PONTOS) and all(isinstance(c, str) for c in X.columns)
    forma = m.representar(curvas, "forma", grade).to_numpy()
    assert np.allclose(forma.min(axis=1), 0) and np.allclose(forma.max(axis=1), 1)


def test_sem_dados_suficientes_explica(tmp_path, nox_sintetico):
    import pandas as pd
    with pytest.raises(ValueError, match="base está vazia"):
        m.treinar(pd.DataFrame())
    s, df = _base(tmp_path, n_eletrodos=2)
    with pytest.raises(ValueError, match="pelo menos 3 medições de branco"):
        m.treinar(df)


def test_poucos_eletrodos_sem_teste_independente(tmp_path, nox_sintetico):
    s, df = _base(tmp_path, n_eletrodos=4)
    c = m.treinar(df, rapido=True, variantes=["curva", "pico"])["cartao"]
    assert c["metricas_teste"] is None and c["referencia"] == "validação cruzada"
    assert "sem teste independente" in c["avisos"][0] and "por eletrodo" in c["validacao"]
    # SISSO só com as medidas do pico
    assert {(x["representacao"], x["algoritmo"]) for x in c["placar"] if x["algoritmo"] == "sisso"} == {("pico", "sisso")}


def test_treino_separa_eletrodos_salva_e_preve(tmp_path, nox_sintetico):
    s, df = _base(tmp_path, n_eletrodos=12)
    p = m.treinar(df, rapido=True, variantes=["curva", "forma"])
    c = p["cartao"]
    assert c["referencia"] == "teste" and c["dados"]["n_ensaios"] == 48 and c["dados"]["n_eletrodos"] == 12
    teste = set(c["dados"]["eletrodos_teste"])
    assert teste and len(teste) < 12 and c["dados"]["n_teste"] == 4 * len(teste)      # eletrodo inteiro no teste
    assert c["ab_referencia"] >= 0.7 and c["confiavel"]
    assert [x["posicao"] for x in c["placar"]] == list(range(1, len(c["placar"]) + 1))
    destino = m.salvar(p, tmp_path / "modelos", s=s)
    assert (destino / "cartao.json").exists() and m.em_uso(tmp_path / "modelos") == c["id"]
    assert m.listar(tmp_path / "modelos")[0]["em_uso"]
    assert db.sql(s, "SELECT algoritmo FROM modelos").iloc[0, 0] == c["algoritmo"]
    pacote = m.carregar(tmp_path / "modelos")
    rng = np.random.default_rng(9)
    assert m.prever_curva(pacote, *curva(rng, True, 50))["resultado"] == "CONTAMINADO"
    assert m.prever_curva(pacote, *curva(rng, False))["resultado"] == "NÃO CONTAMINADO"
    curta = m.prever_curva(pacote, E[E < 0.3], np.ones((E < 0.3).sum()))
    assert curta["resultado"] == "REPETIR MEDIÇÃO" and "o modelo precisa de" in curta["motivo"]
    # arquivos: resultado, pico, curva e o que o nome diz
    a = escrever_nox(tmp_path / "novo" / "dpv-RNA-5,0-E99.nox", "DPV Oligo 4N RNA 5 ng-mL", *curva(rng, True, 5))
    r = m.prever_arquivos(pacote, [a])[0]
    assert r["resultado"] == "CONTAMINADO" and r["tipo_informado"] == "rna" and r["e_pico_v"] and len(r["current_ua"]) == 179
    assert m.gravar_predicoes(s, [r], c) == 1
    assert db.sql(s, "SELECT resultado FROM predicoes").iloc[0, 0] == "CONTAMINADO"


def test_modelo_pouco_confiavel_da_inconclusivo(tmp_path, nox_sintetico):
    s, df = _base(tmp_path, n_eletrodos=12)
    p = m.treinar(df, algoritmos=["log_reg"], variantes=["curva"])
    p["cartao"].update(confiavel=False, ab_referencia=0.55)
    r = m.prever_curva(p, *curva(np.random.default_rng(1), True, 5))
    assert r["resultado"] == "INCONCLUSIVO" and r["prob_contaminado"] is not None and "0.55" in r["motivo"]


def test_qc_fail_fica_fora_do_treino(tmp_path, nox_sintetico):
    s, df = _base(tmp_path, n_eletrodos=4)
    df.loc[df["tipo"] == "branco", "qc_flag"] = "FAIL"
    assert len(m.dados_de_treino(df)) == 12 and set(m.dados_de_treino(df)["tipo"]) == {"rna"}


def test_cli_do_comeco_ao_fim(tmp_path, nox_sintetico, capsys):
    from fiep.cli import main
    gerar_pasta(tmp_path / "rna", n_eletrodos=4)
    banco, modelos = str(tmp_path / "c.db"), str(tmp_path / "modelos")
    assert main(["rna", "importar", "--db", banco, "--entrada", str(tmp_path / "rna")]) == 0
    assert "16 gravado(s)" in capsys.readouterr().out
    assert main(["rna", "treinar", "--db", banco, "--modelos", modelos, "--rapido",
                 "--representacoes", "curva"]) == 0
    assert "sem teste independente" in capsys.readouterr().out
    assert main(["rna", "prever", "--db", banco, "--modelos", modelos, "--salvar",
                 "--entrada", str(tmp_path / "rna" / "contaminado")]) == 0
    saida = capsys.readouterr().out
    assert saida.count("CONTAMINADO") >= 12 and "12 previsão(ões) gravada(s)" in saida
    assert main(["modelos", "listar", "--modelos", modelos]) == 0 and "*" in capsys.readouterr().out
    assert main(["rna", "prever", "--modelos", str(tmp_path / "vazio"), "--entrada", str(tmp_path / "rna")]) == 1
    assert "nenhum modelo em uso" in capsys.readouterr().err


def test_modelo_de_versao_antiga_e_ignorado(tmp_path):
    """Modelos da época do case (cartão em outro formato) não podem derrubar a lista, a tela nem a previsão."""
    import json
    antigo = tmp_path / "20261101-120000"
    antigo.mkdir()
    (antigo / "modelo.joblib").touch()
    (antigo / "cartao.json").write_text(json.dumps({"id": antigo.name, "modelo": "random_forest",
                                                    "metricas_cv": {"balanced_accuracy": 0.9}}))
    (tmp_path / "ATUAL").write_text(antigo.name)
    assert m.listar(tmp_path) == []
    assert m.em_uso(tmp_path) is None
    with pytest.raises(FileNotFoundError, match="versão antiga"):
        m.cartao(antigo.name, tmp_path)
    with pytest.raises(FileNotFoundError, match="versão antiga"):
        m.ativar_modelo(antigo.name, tmp_path)
    with pytest.raises(FileNotFoundError, match="nenhum modelo em uso"):
        m.carregar(tmp_path)
