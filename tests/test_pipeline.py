import numpy as np
import pandas as pd
import pytest

from fiep.config import load_config
from fiep.features import tabela_features
from fiep.ingest import Dataset, classificar, ingerir
from fiep.model import carregar, treinar
from fiep.predict import prever
from fiep.preprocess import curvas_por_medicao, inferir_grade, para_matriz
from fiep.qc import avaliar

from .conftest import gerar_case


def test_classifica_tabelas_pelas_colunas():
    assert classificar(pd.DataFrame(columns=["measurement_id", "potential_v", "current_ua"])) == "sinal"
    assert classificar(pd.DataFrame(columns=["measurement_id", "sample_id", "contamination_status"])) == "metadados"
    assert classificar(pd.DataFrame(columns=["sample_id", "colony_count"])) == "plaqueamento"
    assert classificar(pd.DataFrame(columns=["arquivo", "sample_id"])) == "indice_nox"
    assert classificar(pd.DataFrame(columns=["x", "y"])) is None


def test_ingestao_formato_canonico(pasta_case, tmp_path):
    ds = ingerir(pasta_case)
    assert len(ds.medicoes) == 24 * 2 * 3
    assert {"measurement_id", "potential_v", "current_ua", "scan_index"} <= set(ds.pontos.columns)
    assert ds.medicoes["contamination_status"].notna().all()
    assert "plaqueamento_n_replicatas" in ds.amostras
    ds.salvar(tmp_path / "proc")
    ds2 = Dataset.carregar(tmp_path / "proc")
    assert len(ds2.pontos) == len(ds.pontos)


def test_qc_reprova_sobrecarga_e_potencial_desviado():
    cfg = load_config()
    e = np.linspace(-0.3, 0.6, 100)
    med = pd.DataFrame({"measurement_id": ["ok", "sobre", "desvio", "curta"], "qc_flag": "PASS",
                        "tecnica": "DPV", "sensor_state": "x"})
    pts = pd.concat([
        pd.DataFrame({"measurement_id": "ok", "potential_v": e, "current_ua": 5.0, "e_medido_v": e}),
        pd.DataFrame({"measurement_id": "sobre", "potential_v": e, "current_ua": 5.0, "e_medido_v": e,
                      "i_bruta_ua": 10000.0}),
        pd.DataFrame({"measurement_id": "desvio", "potential_v": e, "current_ua": 5.0,
                      "e_medido_v": np.clip(e, -0.1, 0.1)}),
        pd.DataFrame({"measurement_id": "curta", "potential_v": e[:10], "current_ua": 5.0}),
    ])
    qc = avaliar(med, pts, cfg).set_index("measurement_id")
    assert qc.at["ok", "qc_final"] == "PASS"
    assert qc.at["sobre", "qc_final"] == "FAIL" and "sobrecarga" in qc.at["sobre", "qc_motivos"]
    assert qc.at["desvio", "qc_final"] == "FAIL" and "potencial" in qc.at["desvio", "qc_motivos"]
    assert qc.at["curta", "qc_final"] == "FAIL"


def test_qc_respeita_flag_da_planilha(pasta_case):
    ds = ingerir(pasta_case)
    ds.medicoes.loc[0, "qc_flag"] = "REVIEW"
    qc = avaliar(ds.medicoes, ds.pontos, load_config())
    assert qc.loc[qc.measurement_id == ds.medicoes.loc[0, "measurement_id"], "qc_final"].item() == "REVIEW"


def test_grade_e_interpolacao():
    cfg = load_config()
    curvas = {"a": (np.linspace(-0.3, 0.6, 181), np.ones(181)), "b": (np.linspace(-0.2, 0.5, 141), np.ones(141))}
    grade = inferir_grade(curvas, cfg)
    assert grade[0] == pytest.approx(-0.2) and grade[-1] == pytest.approx(0.5)
    m = para_matriz(curvas, grade, cfg)
    assert m.shape == (2, len(grade)) and not m.isna().any().any()


def test_features_exigem_todos_os_estagios(pasta_case):
    cfg = load_config()
    ds = ingerir(pasta_case)
    ids = set(ds.medicoes.measurement_id) - {"S000_R1_2"}      # tira um estágio de uma réplica
    curvas = curvas_por_medicao(ds.pontos, ids, cfg)
    tab = tabela_features(para_matriz(curvas, inferir_grade(curvas, cfg), cfg), ds.medicoes, cfg)
    assert len(tab) == 24 * 2 - 1
    assert any(c.startswith("delta_i_pico") for c in tab.columns)


def test_treino_registra_modelo_e_predicao_reusa_grade(pasta_case, tmp_path):
    cfg = load_config()
    cfg["modelo"]["candidatos"] = ["log_reg", "random_forest"]
    ds = ingerir(pasta_case)
    r = treinar(ds, cfg, tmp_path / "modelos")
    assert (r["pasta"] / "modelo.joblib").exists() and (r["pasta"] / "cartao.json").exists()
    assert (tmp_path / "modelos" / "registro.csv").exists()
    assert r["cartao"]["metricas_cv"]["balanced_accuracy"] > 0.8      # efeito sintético é forte

    pacote = carregar(tmp_path / "modelos")
    # nova coleta com grade de potencial diferente: a predição interpola para a grade do treino
    sinal, meta, _ = gerar_case(n_amostras=6, seed=1, e=np.round(np.arange(-0.3, 0.6001, 0.004), 3))
    nova = tmp_path / "nova"
    nova.mkdir()
    sinal.to_csv(nova / "sinal.csv", index=False)
    meta.to_csv(nova / "meta.csv", index=False)
    res = prever(nova, pacote)
    avaliadas = res[res.status == "avaliada"]
    assert len(avaliadas) == 12
    acerto = ((avaliadas.prob_contaminada >= pacote["limiar"]).astype(int) == avaliadas.rotulo_informado).mean()
    assert acerto >= 0.9


def test_predicao_explica_replicata_incompleta(pasta_case, tmp_path):
    cfg = load_config()
    cfg["modelo"]["candidatos"] = ["log_reg"]
    treinar(ingerir(pasta_case), cfg, tmp_path / "m")
    sinal, meta, _ = gerar_case(n_amostras=1, n_rep=1, seed=3)
    keep = meta.sensor_state != "carbon_clean"
    d = tmp_path / "inc"
    d.mkdir()
    sinal[sinal.measurement_id.isin(meta[keep].measurement_id)].to_csv(d / "s.csv", index=False)
    meta[keep].to_csv(d / "m.csv", index=False)
    res = prever(d, carregar(tmp_path / "m"))
    # modelo do `fiep treinar` não tem modelos de etapa única: explica o que falta e como resolver
    assert res.iloc[0]["status"] == "incompleta" and "Carbono limpo" in res.iloc[0]["motivo"]
    assert "treine de novo" in res.iloc[0]["motivo"]
