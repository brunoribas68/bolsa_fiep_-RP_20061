import pytest

from fiep.config import load_config
from fiep.divisao import de_pastas, dividir, montar, proporcoes
from fiep.ingest import ingerir

from .conftest import gerar_case


def _salvar(pasta, n, prefixo="", seed=0):
    sinal, meta, plaq = gerar_case(n_amostras=n, seed=seed)
    for df in (sinal, meta):
        df["measurement_id"] = prefixo + df["measurement_id"]
    meta["sample_id"] = prefixo + meta["sample_id"]
    pasta.mkdir(parents=True, exist_ok=True)
    sinal.to_csv(pasta / f"{prefixo}sinal.csv", index=False)
    meta.to_csv(pasta / f"{prefixo}meta.csv", index=False)
    return pasta


def _classes(ds):
    return set(ds.medicoes.groupby("sample_id")["contamination_status"].max())


def test_proporcoes_padrao_50_25_25():
    assert proporcoes(load_config()) == {"treino": 0.5, "validacao": 0.25, "teste": 0.25}


def test_dividir_por_amostra_estratificado(pasta_case):
    ds = ingerir(pasta_case)
    p = dividir(ds, proporcoes(None), seed=1)
    assert [len(p[k]) for k in ("treino", "validacao", "teste")] == [12, 6, 6]
    assert not (p["treino"] & p["validacao"]) and not (p["treino"] & p["teste"]) and not (p["validacao"] & p["teste"])
    rot = ds.medicoes.groupby("sample_id")["contamination_status"].max()
    for k in p:                                      # as duas classes em todos os conjuntos
        assert set(rot[list(p[k])]) == {0, 1}


def test_dados_soltos_sao_divididos(tmp_path):
    _salvar(tmp_path / "dados", 24)
    d = de_pastas(tmp_path / "dados", load_config())
    assert (d.amostras("treino"), d.amostras("validacao"), d.amostras("teste")) == (12, 6, 6)
    assert "50/25/25" in d.descricao()


def test_pastas_sao_somadas_ao_conjunto(tmp_path):
    base = tmp_path / "dados"
    _salvar(base, 24)
    _salvar(base / "teste", 9, prefixo="EXT", seed=3)
    _salvar(base / "exemplo_case", 30, prefixo="EX", seed=4)          # nunca entra quando há dados
    d = de_pastas(base, load_config())
    assert d.amostras("teste") == 6 + 9
    assert {s for s in d.teste.medicoes["sample_id"] if s.startswith("EXT")} == {f"EXTS{i:03d}" for i in range(9)}
    assert not any(s.startswith("EX") for k in ("treino", "validacao") for s in d[k].medicoes["sample_id"])
    assert d.origem["teste"] == {"sorteadas de dados/": 6, "da pasta teste/": 9}


def test_so_pasta_de_treino_sorteia_validacao_e_teste(tmp_path):
    _salvar(tmp_path / "dados" / "treino", 24)
    d = de_pastas(tmp_path / "dados", load_config())
    assert (d.amostras("treino"), d.amostras("validacao"), d.amostras("teste")) == (12, 6, 6)
    assert _classes(d.validacao) == _classes(d.teste) == {0, 1}


def test_sem_dados_usa_exemplo_case(tmp_path):
    _salvar(tmp_path / "dados" / "exemplo_case", 24)
    (tmp_path / "dados" / "treino").mkdir()
    d = de_pastas(tmp_path / "dados", load_config())
    assert d.amostras("treino") == 12


def test_amostra_em_duas_pastas_e_erro(tmp_path):
    ds = ingerir(_salvar(tmp_path / "a", 6))
    with pytest.raises(ValueError, match="mais de uma pasta"):
        montar(None, {"treino": ds, "teste": ds})


def test_sem_rotulo_explica_o_que_falta(tmp_path):
    sinal, meta, _ = gerar_case(n_amostras=4)
    meta["sample_id"] = None                        # planilha ainda não preenchida
    pasta = tmp_path / "dados" / "empresa1"
    pasta.mkdir(parents=True)
    sinal.to_csv(pasta / "s.csv", index=False)
    meta.to_csv(pasta / "m.csv", index=False)
    with pytest.raises(ValueError, match="sem sample_id"):
        de_pastas(tmp_path / "dados", load_config())


def test_so_um_estagio_explica_os_estagios(pasta_case):
    from fiep.divisao import diagnosticar
    ds = ingerir(pasta_case)
    ds.medicoes = ds.medicoes[ds.medicoes.sensor_state == "capture_probe_16S_rRNA"]
    msg = diagnosticar(ds, load_config())
    assert "0 de" in msg and "precisa dos três" in msg
