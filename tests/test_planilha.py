import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from fiep.planilha import gerar_planilha, sugerir_estagio


def test_sugere_estagio_pelo_nome():
    assert sugerir_estagio("DPV_SPCE_Oligo_5N__rRNA_1") == "capture_probe_16S_rRNA"
    assert sugerir_estagio("eletrodo3_sonda") == "capture_probe"
    assert sugerir_estagio("E3_limpo") == "carbon_clean"
    assert sugerir_estagio("medida_42") is None


PASTA = os.environ.get("FIEP_NOX_DIR")


@pytest.mark.skipif(not PASTA, reason="defina FIEP_NOX_DIR com .nox reais para rodar")
def test_planilha_lista_nox_e_so_acrescenta_novos(tmp_path):
    arqs = sorted(Path(PASTA).glob("*.nox"))[:3]
    (tmp_path / "sub").mkdir()
    shutil.copy(arqs[0], tmp_path)
    shutil.copy(arqs[1], tmp_path / "sub")
    destino, n = gerar_planilha(tmp_path)
    assert n == 2
    df = pd.read_csv(destino, dtype=str)
    assert set(df["arquivo"]) == {arqs[0].name, f"sub/{arqs[1].name}"}
    assert df["tecnica"].notna().all()
    df.loc[0, "sample_id"] = "X1"                      # usuário preenche
    df.to_csv(destino, index=False)
    shutil.copy(arqs[2], tmp_path)
    _, n2 = gerar_planilha(tmp_path)
    df2 = pd.read_csv(destino, dtype=str)
    assert n2 == 1 and len(df2) == 3 and df2.loc[0, "sample_id"] == "X1"
