import json

import numpy as np
import pandas as pd

from fiep.config import load_config
from fiep.divisao import montar
from fiep.experimentos import rodar
from fiep.ingest import ingerir
from fiep.model import carregar
from fiep.predict import prever, resumo_por_amostra
from fiep.sisso import SissoClassificador

from .conftest import gerar_case


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
    assert res["amostras_teste"] > 0 and res["amostras_validacao"] > 0 and res["modelo_registrado"]
    assert res["criterio_escolha"] == "acurácia balanceada na validação"
    pl = r["placar"]
    assert pl["val_balanced_accuracy"].iloc[0] == pl["val_balanced_accuracy"].max()   # escolha pela validação
    assert "\\ABval" in (pasta / "tabelas" / "numeros.tex").read_text(encoding="utf-8")

    # o modelo registrado é o que a predição (e a API) usa, com a carga estimada
    pacote = carregar(tmp_path / "modelos")
    sinal, meta, _ = gerar_case(n_amostras=3, seed=9)
    nova = tmp_path / "nova"
    nova.mkdir()
    sinal.to_csv(nova / "s.csv", index=False)
    meta.drop(columns="contamination_status").assign(contamination_status=np.nan).to_csv(nova / "m.csv", index=False)
    out = prever(nova, pacote)
    assert (out["status"] == "avaliada").all()
    assert (out["base"] == "etapas completas").all()

    # eletrodo só com a 1ª etapa (ex.: só o eletrodo tratado): previsão pelo modelo daquela etapa, com aviso
    assert set(res["por_etapa"]) == {"carbon_clean", "capture_probe", "capture_probe_16S_rRNA"}
    assert "carbon_clean" in pacote["por_etapa"]
    so1 = tmp_path / "so_primeira"
    so1.mkdir()
    um = meta[meta["sensor_state"] == "carbon_clean"]
    sinal[sinal["measurement_id"].isin(um["measurement_id"])].to_csv(so1 / "s.csv", index=False)
    um.drop(columns="contamination_status").assign(contamination_status=np.nan).to_csv(so1 / "m.csv", index=False)
    o1 = prever(so1, pacote)
    assert o1["base"].str.startswith("etapa única").all() and o1["prob_contaminada"].notna().all()
    assert o1["motivo"].str.contains("previsão só com a etapa Carbono limpo").all()
    # a etapa do eletrodo limpo não separa as classes no case: o resultado sai inconclusivo, e não um palpite
    ba = res["por_etapa"]["carbon_clean"]["teste_balanced_accuracy"]
    esperado = "inconclusiva" if ba < 0.7 else "avaliada"
    assert (o1["status"] == esperado).all()
    am = resumo_por_amostra(o1)
    assert (am["base"] == "etapa única").all()
    assert am["resultado"].isin(["INCONCLUSIVO"] if ba < 0.7 else ["CONTAMINADA", "NÃO CONTAMINADA"]).all()


def test_experimento_com_pasta_de_teste(pasta_case, tmp_path):
    sinal, meta, plaq = gerar_case(n_amostras=9, seed=5)
    meta["sample_id"] = "V" + meta["sample_id"]
    meta["measurement_id"] = "V" + meta["measurement_id"]
    sinal["measurement_id"] = "V" + sinal["measurement_id"]
    val = tmp_path / "val"
    val.mkdir()
    sinal.to_csv(val / "s.csv", index=False)
    meta.to_csv(val / "m.csv", index=False)
    div = montar(ingerir(pasta_case), {"teste": ingerir(val)}, load_config())
    r = rodar(div, load_config(), saida=tmp_path / "r", pasta_modelos=tmp_path / "m", rapido=True,
              variantes=["dif_resumo"])
    assert r["resumo"]["amostras_teste"] == 6 + 9          # 25% sorteado + pasta de teste
    assert "da pasta teste/" in r["resumo"]["teste"]
