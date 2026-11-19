"""Pico do DPV, inclusive com a corrente subindo na ponta da varredura."""
import numpy as np

from fiep.pico import medir_pico


def test_pico_ignora_a_subida_na_ponta():
    e = np.linspace(-0.3, 0.6, 180)
    i = 18 + 5 * np.exp(-((e - 0.15) / 0.05) ** 2) + np.where(e > 0.4, (e - 0.4) * 40, 0)
    assert i.argmax() == len(i) - 1                    # o máximo absoluto é a ponta, não o pico
    p = medir_pico(e, i)
    assert abs(p["e_pico_v"] - 0.15) < 0.01 and abs(p["altura_ua"] - 5) < 0.3 and 0.05 < p["largura_v"] < 0.12


def test_curva_curta_nao_tem_pico():
    assert medir_pico([0, 0.1, 0.2], [1, 2, 1]) == {}
