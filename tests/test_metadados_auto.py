from pathlib import Path

import pandas as pd

from fiep.ingest import _completar_por_amostra, Relatorio
from fiep.metadados_auto import inferir, tabela_amostras

ESTAGIOS = ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"]


def _info(canal, proc="DPV FF 2,5 mM", data="2026-02-23 18:23:24"):
    return {"instrumento": f"MAC80058#{canal}", "procedimento": proc, "data_hora_procedimento": data}


def test_lote_organizado_por_pastas_e_deduzido_sem_planilha():
    arqs, infos = [], {}
    for rot in ("contaminada", "nao_contaminada"):
        for am in ("A01", "A02"):
            for est in ("limpo", "sonda", "rRNA"):
                for canal in ("1", "2"):
                    p = Path(f"empresa1/{rot}/{am}/DPV_{est}_{canal}.nox")
                    arqs.append(p)
                    infos[p] = _info(canal)
    df = inferir(arqs, infos)
    assert df["sample_id"].nunique() == 4                      # A01 existe nas duas pastas: não mistura
    assert "contaminada_A01" in set(df["sample_id"]) and "nao_contaminada_A01" in set(df["sample_id"])
    assert set(df["sensor_state"]) == set(ESTAGIOS)
    assert set(df["replicate_id"]) == {"1", "2"}
    rot = df.groupby(df["_caminho"].map(lambda p: p.parts[1]))["contamination_status"].first()
    assert rot["contaminada"] == 1 and rot["nao_contaminada"] == 0          # "nao_" vence "contaminada"
    assert (df["measurement_date"] == "2026-02-23").all()
    assert df["measurement_id"].is_unique
    am = tabela_amostras(df.assign(sample_id=df["_caminho"].map(lambda p: p.parts[2] + p.parts[1][:3])), ESTAGIOS)
    assert len(am) == 4 and (am["observacoes"] == "").all()


def test_procedimento_define_estagio_quando_o_nome_nao_diz():
    p = Path("lote/medida_7.nox")
    df = inferir([p], {p: _info("B", proc="DPV FF 2,5 mM SPCE Oligo 5N + rRNA")})
    assert df.loc[0, "sensor_state"] == "capture_probe_16S_rRNA" and df.loc[0, "replicate_id"] == "B"


def test_pasta_plana_com_varias_sessoes_separa_por_dia():
    arqs, infos = [], {}
    for dia in ("2026-03-01", "2026-03-02"):
        for est in ("limpo", "rRNA"):
            p = Path(f"lote/{dia}_{est}.nox")
            arqs.append(p)
            infos[p] = _info("1", data=f"{dia} 10:00:00")
    df = inferir(arqs, infos)
    assert set(df["sample_id"]) == {"lote_20260301", "lote_20260302"}


def test_padrao_de_nome_configuravel():
    p = Path("x/EMP1-S07-R3-sonda.nox")
    cfg = {"metadados": {"padrao_nome": r"(?P<sample_id>EMP\d+-S\d+)-R(?P<replicate_id>\d+)"}}
    df = inferir([p], {p: _info("1")}, cfg)
    assert df.loc[0, "sample_id"] == "EMP1-S07" and df.loc[0, "replicate_id"] == "3"
    assert df.loc[0, "sensor_state"] == "capture_probe"


def test_tabela_de_amostras_completa_rotulo_e_carga():
    med = pd.DataFrame({"sample_id": ["A", "A", "B"], "contamination_status": [None, None, 0]})
    rot = pd.DataFrame({"sample_id": ["A", "B"], "contamination_status": [1, 1], "sample_log10_mean_cfu_ml": [5.1, 0]})
    out = _completar_por_amostra(med, rot, Relatorio())
    assert list(out["contamination_status"]) == [1, 1, 0]                   # o da medição vence
    assert list(out["sample_log10_mean_cfu_ml"]) == [5.1, 5.1, 0]
