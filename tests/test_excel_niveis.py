import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fiep.ingest import ingerir
from fiep.predict import nivel, resumo_por_amostra

from .conftest import gerar_case

CFG = {"niveis": {"limites_log10": [3.0, 5.0], "nomes": ["baixa", "moderada", "alta"]}}


def test_niveis_pela_carga():
    assert nivel(None, CFG) == "não detectada"
    assert [nivel(x, CFG) for x in (1.0, 3.0, 4.9, 5.0, 7.2)] == ["baixa", "moderada", "moderada", "alta", "alta"]
    assert nivel(4.0, {}) == "detectada"                         # sem limites: só detectada/não detectada


def test_exportacao_nova_em_excel_e_csv_e_lida_como_o_nox(tmp_path):
    """Pesquisador manda o Excel/CSV exportado do NOVA em vez do .nox: uma pasta por amostra."""
    sinal, meta, _ = gerar_case(n_amostras=2, n_rep=1)
    nomes = {"carbon_clean": "limpo", "capture_probe": "sonda", "capture_probe_16S_rRNA": "rRNA"}
    for i, (mid, g) in enumerate(sinal.groupby("measurement_id")):
        m = meta.set_index("measurement_id").loc[mid]
        pasta = tmp_path / "lote" / ("contaminada" if m.contamination_status else "nao_contaminada") / m.sample_id
        pasta.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame({"Index": range(1, len(g) + 1), "Potential applied (V)": g["potential_V"].to_numpy(),
                           "WE(1).δ.Current (A)": g["current_uA"].to_numpy() * 1e-6})
        nome = f"DPV_{nomes[m.sensor_state]}_1"
        if i % 2:
            df.to_excel(pasta / f"{nome}.xlsx", index=False)
        else:                                      # CSV do Excel em português: ; e vírgula decimal
            df.to_csv(pasta / f"{nome}.csv", sep=";", decimal=",", index=False)
    ds = ingerir(tmp_path / "lote")
    med = ds.medicoes
    assert len(med) == 6 and (med["fonte"] == "exportacao").all()
    assert set(med["sensor_state"]) == {"carbon_clean", "capture_probe", "capture_probe_16S_rRNA"}
    assert med.groupby("sample_id")["contamination_status"].first().to_dict() == {"S000": 0, "S001": 1}
    orig = sinal[sinal.measurement_id == "S001_R1_2"]["current_uA"].to_numpy()
    lido = ds.pontos[ds.pontos.measurement_id == med.loc[(med.sample_id == "S001") &
                     (med.sensor_state == "capture_probe_16S_rRNA"), "measurement_id"].iloc[0]]["current_ua"]
    assert np.allclose(lido.to_numpy(), orig)


def test_resumo_por_amostra_junta_replicas():
    res = pd.DataFrame({
        "sample_id": ["A", "A", "A", "B"], "replicate_id": [1, 2, 3, 1],
        "status": ["avaliada", "avaliada", "reprovada no QC (FAIL)", "avaliada"],
        "prob_contaminada": [0.9, 0.7, np.nan, 0.1], "log10_ufc_ml_estimado": [5.5, 4.5, np.nan, np.nan],
        "resultado": ["CONTAMINADA", "CONTAMINADA", "REPETIR MEDIÇÃO", "NÃO CONTAMINADA"],
        "rotulo_informado": [np.nan] * 4})
    am = resumo_por_amostra(res, limiar=0.5, cfg=CFG).set_index("sample_id")
    assert am.loc["A", "resultado"] == "CONTAMINADA" and am.loc["A", "replicas_avaliadas"] == 2
    assert am.loc["A", "replicas_total"] == 3 and am.loc["A", "nivel_contaminacao"] == "alta"          # média 5,0 = limite de "alta"
    assert am.loc["B", "nivel_contaminacao"] == "não detectada"


PASTA = os.environ.get("FIEP_NOX_DIR")


@pytest.mark.skipif(not PASTA, reason="defina FIEP_NOX_DIR com .nox reais para rodar")
def test_nox_para_excel_ida_e_volta(tmp_path):
    import shutil

    from fiep.excel import converter_pasta
    (tmp_path / "A01").mkdir()
    for f in sorted(Path(PASTA).glob("DPV*.nox"))[:2]:
        shutil.copy(f, tmp_path / "A01")
    gerados = converter_pasta(tmp_path / "A01", tmp_path / "excel" / "A01")
    assert len(gerados) == 2
    a, b = ingerir(tmp_path / "A01"), ingerir(tmp_path / "excel" / "A01")
    cols = ["measurement_id", "sample_id", "replicate_id", "sensor_state", "tecnica"]
    pd.testing.assert_frame_equal(a.medicoes[cols].reset_index(drop=True), b.medicoes[cols].reset_index(drop=True))
    assert np.allclose(a.pontos["current_ua"], b.pontos["current_ua"])
