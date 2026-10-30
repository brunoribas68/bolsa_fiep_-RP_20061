"""Picos dos voltamogramas (DPV e CV), inclusive com a corrente subindo nas pontas da varredura."""
import numpy as np
import pandas as pd

from fiep.features import descritores
from fiep.picos import picos


def _dpv_com_rampa():
    e = np.linspace(-0.3, 0.6, 180)
    i = 18 + 5 * np.exp(-((e - 0.15) / 0.05) ** 2) + np.where(e > 0.4, (e - 0.4) * 40, 0)  # sobe no fim
    return e, i


def _cv():
    ida = np.linspace(0.6, -0.3, 300)          # começa descendo (catódica) e volta (anódica)
    volta = ida[::-1]
    ic = -60 * np.exp(-((ida - 0.07) / 0.06) ** 2) - 20 * (ida < -0.25)   # cauda na ponta
    ia = 55 * np.exp(-((volta - 0.21) / 0.06) ** 2) + 30 * (volta > 0.55)
    return np.r_[ida, volta], np.r_[ic, ia]


def test_pico_dpv_ignora_a_subida_na_ponta():
    e, i = _dpv_com_rampa()
    assert i.argmax() == len(i) - 1                    # o máximo absoluto é a ponta, não o pico
    d = descritores(e, i, "s")
    assert abs(d["s_e_pico"] - 0.15) < 0.01


def test_picos_dpv_e_cv():
    e1, i1 = _dpv_com_rampa()
    e2, i2 = _cv()
    med = pd.DataFrame({"measurement_id": ["d", "c"], "sample_id": "A", "replicate_id": "1",
                        "sensor_state": "carbon_clean", "tecnica": ["DPV", "CV"], "arquivo_origem": ["d.xlsx", "c.xlsx"]})
    pts = pd.concat([pd.DataFrame({"measurement_id": "d", "potential_v": e1, "current_ua": i1, "scan_index": 1}),
                     pd.DataFrame({"measurement_id": "c", "potential_v": e2, "current_ua": i2, "scan_index": 1})])
    p = picos(med, pts).set_index("measurement_id")
    assert abs(p.at["d", "e_pico_v"] - 0.15) < 0.01 and abs(p.at["d", "altura_ua"] - 5) < 0.5
    assert abs(p.at["c", "epa_v"] - 0.21) < 0.01 and abs(p.at["c", "epc_v"] - 0.07) < 0.01
    assert abs(p.at["c", "delta_ep_v"] - 0.14) < 0.015 and abs(p.at["c", "e_meia_v"] - 0.14) < 0.01
