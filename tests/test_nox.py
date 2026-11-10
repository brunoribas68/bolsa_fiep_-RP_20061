"""Testes do leitor .nox.

O teste do formato binário usa um fluxo NRBF mínimo montado aqui. Os testes com
arquivos reais rodam só se a variável FIEP_NOX_DIR apontar para uma pasta com .nox
(os arquivos do projeto não são versionados).
"""
import os
import struct
from pathlib import Path

import pytest

from fiep.io.nrbf import read_all


def _string(s: str) -> bytes:
    b = s.encode()
    return bytes([len(b)]) + b


def test_nrbf_fluxo_minimo():
    cabecalho = b"\x00" + struct.pack("<iiii", 1, -1, 1, 0)
    texto = b"\x06" + struct.pack("<i", 1) + _string("NOVA")
    arr = b"\x0f" + struct.pack("<ii", 2, 3) + b"\x06" + struct.pack("<3d", 1.0, 2.0, 3.5)
    fim = b"\x0b"
    streams = read_all(cabecalho + texto + fim + cabecalho + arr + fim)
    assert len(streams) == 2
    assert streams[0][1][1] == "NOVA"
    assert streams[1][1][2].items == [1.0, 2.0, 3.5]


PASTA = os.environ.get("FIEP_NOX_DIR")


@pytest.mark.skipif(not PASTA, reason="defina FIEP_NOX_DIR com .nox reais para rodar")
def test_nox_reais_convertem():
    from fiep.io.nox import nox_to_curves
    arquivos = sorted(Path(PASTA).glob("*.nox"))
    assert arquivos
    for a in arquivos:
        info, curvas = nox_to_curves(a)
        assert info["leitura"] == "completa", a.name
        assert curvas and len(curvas[0]["potential_v"]) == len(curvas[0]["current_ua"]) > 10
        assert curvas[0]["tecnica"] in {"DPV", "SWV", "CV", "LSV"}


def test_conversor_cv_fica_com_o_ultimo_scan():
    """nox2excel: CV com vários ciclos sai só com o último scan (ou o escolhido); DPV não muda."""
    import sys
    import pandas as pd
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from nox2excel import filtrar_scan
    cv = pd.DataFrame({"Potential applied (V)": range(12), "Scan": [1] * 4 + [2] * 4 + [3] * 4})
    assert filtrar_scan(cv)[0]["Scan"].unique().tolist() == [3]
    assert filtrar_scan(cv, "2")[0]["Scan"].unique().tolist() == [2]
    assert len(filtrar_scan(cv, "todos")[0]) == 12
    df, nota = filtrar_scan(cv, "9")
    assert df["Scan"].unique().tolist() == [3] and "não existe" in nota
    dpv = pd.DataFrame({"Potential applied (V)": range(5)})
    assert filtrar_scan(dpv)[0] is dpv and filtrar_scan(dpv)[1] is None
