import json

import numpy as np
import pandas as pd

from fiep.config import load_config
from fiep.experimentos import rodar, separar_teste
from fiep.ingest import ingerir
from fiep.model import carregar
from fiep.predict import prever
from fiep.sisso import SissoClassificador

from .conftest import gerar_case


def test_teste_separado_por_amostra(pasta_case):
    ds = ingerir(pasta_case)
    tr, te = separar_teste(ds, 0.25, seed=1)
    assert tr and te and not (tr & te)
    rotulo = ds.medicoes.groupby("sample_id")["contamination_status"].max()
    assert set(rotulo[list(te)]) == {0, 1}          # estratificado: as duas classes no teste


def test_sisso_acha_descritor_simples():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(200, 6)), columns=[f"x{i}" for i in range(6)])
    y = ((X["x1"] - X["x4"]) > 0).astype(int).to_numpy()
    m = SissoClassificador(n_sis=10, max_dim=1).fit(X, y)
    assert m.descritor_ in {("(x1-x4)",), ("(x4-x1)",)}      # o sinal vai para o coeficiente
    assert (m.predict(X) == y).mean() > 0.95
    assert m.descritor_[0].strip("()") in m.formula()


def test_experimento_rapido_registra_modelo_e_gera_artefatos(pasta_case, tmp_path):
    cfg = load_config()
    r = rodar(ingerir(pasta_case), cfg, saida=tmp_path / "res", pasta_modelos=tmp_path / "modelos",
              rapido=True, variantes=["dif_resumo"])
    pasta = r["pasta"]
    assert (pasta / "classificacao.csv").exists()
    assert (pasta / "tabelas" / "numeros.tex").exists()
    assert (pasta / "figuras" / "comparacao_modelos.png").exists()
    res = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
    assert res["amostras_teste"] > 0 and res["modelo_registrado"]
    assert r["placar"]["cv_balanced_accuracy"].iloc[0] >= r["placar"]["cv_balanced_accuracy"].iloc[-1]

    # o modelo registrado é o que a predição (e a API) usa, com a carga estimada
    pacote = carregar(tmp_path / "modelos")
    sinal, meta, _ = gerar_case(n_amostras=3, seed=9)
    nova = tmp_path / "nova"
    nova.mkdir()
    sinal.to_csv(nova / "s.csv", index=False)
    meta.drop(columns="contamination_status").assign(contamination_status=np.nan).to_csv(nova / "m.csv", index=False)
    out = prever(nova, pacote)
    assert (out["status"] == "avaliada").all()


def test_experimento_com_validacao_externa(pasta_case, tmp_path):
    sinal, meta, plaq = gerar_case(n_amostras=9, seed=5)
    meta["sample_id"] = "V" + meta["sample_id"]
    meta["measurement_id"] = "V" + meta["measurement_id"]
    sinal["measurement_id"] = "V" + sinal["measurement_id"]
    val = tmp_path / "val"
    val.mkdir()
    sinal.to_csv(val / "s.csv", index=False)
    meta.to_csv(val / "m.csv", index=False)
    r = rodar(ingerir(pasta_case), load_config(), ingerir(val), saida=tmp_path / "r",
              pasta_modelos=tmp_path / "m", rapido=True, variantes=["dif_resumo"])
    assert "externa" in r["resumo"]["teste"]
    assert r["resumo"]["amostras_teste"] == 9
