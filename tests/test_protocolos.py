"""Protocolos de biossensor: o imunossensor NS1 (bloqueio -> mAb-NS1 -> final, SWV) e o do case."""
import pandas as pd

from fiep.config import load_config
from fiep.experimentos import rodar
from fiep.ingest import ingerir
from fiep.metadados_auto import inferir
from fiep.protocolos import ajustar, detectar, estagio
from pathlib import Path

NS1 = {"carbon_clean": "bloqueio", "capture_probe": "mAb_NS1", "capture_probe_16S_rRNA": "final"}


def test_estagios_pelo_nome():
    assert estagio("bloqueio-E1") == "bloqueio"
    assert estagio("mAb-NS1-E7") == "mAb_NS1"
    assert estagio("final-E10") == "final"
    assert estagio("DPV_FF_25_mM_SPCE_Oligo_5N__rRNA_1") == "capture_probe_16S_rRNA"
    assert estagio("procedimento-SWV-Hochuen") is None


def test_eletrodo_pelo_nome_vence_o_canal():
    arqs = [Path(f"lote/{e}-E{j}.nox") for j in (1, 2, 10) for e in ("bloqueio", "mAb-NS1", "final")]
    infos = {a: {"instrumento": "MAC80058#1", "procedimento": "procedimento-SWV-Hochuen"} for a in arqs}
    df = inferir(arqs, infos)
    assert set(df["replicate_id"]) == {"E1", "E2", "E10"}               # todos no canal 1, eletrodos diferentes
    assert df.groupby("replicate_id")["sensor_state"].apply(set).map(len).eq(3).all()


def test_protocolo_detectado_e_gravado_no_modelo(pasta_case, tmp_path):
    ds = ingerir(pasta_case)
    ds.medicoes["sensor_state"] = ds.medicoes["sensor_state"].map(NS1)
    ds.medicoes["tecnica"] = "SWV"
    assert detectar(ds.medicoes) == "ns1"
    cfg = ajustar(load_config(), ds)
    assert cfg["dados"]["estagios"] == ["bloqueio", "mAb_NS1", "final"] and cfg["dados"]["tecnica"] == "SWV"
    r = rodar(ds, load_config(), saida=tmp_path / "r", pasta_modelos=tmp_path / "m", rapido=True,
              variantes=["dif_resumo"])
    from fiep.model import carregar
    pac = carregar(tmp_path / "m")
    assert pac["cfg"]["dados"]["protocolo"] == "ns1"
    assert any("final_vs_mAb_NS1" in f for f in pac["features"])        # diferença final - etapa anterior
    assert r["resumo"]["melhor"]["cv_balanced_accuracy"] > 0.8
