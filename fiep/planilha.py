"""Gera (ou completa) as planilhas de um lote de arquivos .nox — já preenchidas.

    fiep planilha --entrada dados/empresa1

Cria duas tabelas na pasta:

* `metadados_nox.csv` — uma linha por .nox, com amostra, réplica (canal), estágio do sensor, data,
  técnica e controle de qualidade **deduzidos automaticamente** (ver `fiep/metadados_auto.py`).
  Serve só para conferir: corrija o que estiver errado; o que a pipeline deduz não precisa ser
  digitado. A coluna `preenchido_auto` diz quais campos foram deduzidos.
* `amostras.csv` — **uma linha por amostra**: é aqui que entra o que não sai do voltamograma,
  o resultado do plaqueamento (`contamination_status` 0/1 e `sample_log10_mean_cfu_ml`). Se o nome
  da pasta já disser (`contaminada/`, `nao_contaminada/`, `controle_neg/`...), vem preenchido.

Rodar de novo acrescenta só os arquivos/amostras novos, sem mexer no que já foi preenchido.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .config import load_config
from .io.nox import nox_to_curves
from .metadados_auto import estagio, inferir, tabela_amostras

COLUNAS = [
    "arquivo", "measurement_id", "sample_id", "replicate_id", "sensor_state", "contamination_status",
    "sample_log10_mean_cfu_ml", "qc_flag", "target_bacterium", "surface_type", "sensor_lot",
    "experimental_batch", "operator_id", "measurement_date",
    # preenchidas automaticamente, só para conferência
    "tecnica", "n_pontos", "qc_automatico", "preenchido_auto", "observacoes",
]
ESTAGIOS_PADRAO = ["carbon_clean", "capture_probe", "capture_probe_16S_rRNA"]

def sugerir_estagio(nome: str) -> str | None:
    return estagio(nome)


def _qc_rapido(curva: dict, cfg: dict) -> str:
    q = cfg["qc"]
    motivos = []
    ib = curva.get("i_bruta_ua") or curva["current_ua"]
    imax = max(abs(v) for v in ib if v == v) if ib else 0
    if imax > q["max_abs_corrente_ua"]:
        motivos.append(f"sobrecarga ({imax:.0f} µA)")
    em = curva.get("e_medido_v")
    if em:
        difs = [b - a for a, b in zip(curva["potential_v"], em) if b == b]
        med = sorted(difs)[len(difs) // 2] if difs else 0.0       # desconta a amplitude do pulso (SWV)
        dev = [abs(d - med) > q["max_desvio_e_v"] for d in difs]
        if dev and sum(dev) / len(dev) > q["max_frac_desvio_e"]:
            motivos.append("potencial medido longe do aplicado")
    if len(curva["potential_v"]) < q["min_pontos"]:
        motivos.append("poucos pontos")
    return "FAIL: " + "; ".join(motivos) if motivos else "PASS"


def _ler(destino: Path, colunas: list[str]) -> pd.DataFrame:
    if not destino.exists():
        return pd.DataFrame(columns=colunas)
    try:
        return pd.read_csv(destino, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(destino, dtype=str, sep=None, engine="python", encoding="cp1252")


def _exportacoes(pasta: Path) -> dict:
    """Excel/CSV exportados do NOVA na pasta (que não sejam cópia de um .nox): {caminho: (info, [curva])}."""
    from .ingest import EXT_TABELA
    from .io.nox import exportacao_to_curves
    stems = {p.stem for p in pasta.rglob("*.nox")}
    out = {}
    for arq in sorted(p for p in pasta.rglob("*") if p.suffix.lower() in EXT_TABELA):
        if arq.name in {"metadados_nox.csv", "amostras.csv"}:
            continue
        try:
            for nome, info, curva in exportacao_to_curves(arq):
                if nome not in stems:
                    out[arq.parent / f"{nome}{arq.suffix}"] = (info, [curva])
        except Exception:  # noqa: BLE001
            continue
    return out


def gerar_planilha(pasta: str | Path, nome: str = "metadados_nox.csv", cfg: dict | None = None) -> tuple[Path, int]:
    """Cria/atualiza `metadados_nox.csv` e `amostras.csv`. Devolve (caminho da planilha, nº de linhas novas)."""
    pasta = Path(pasta)
    cfg = cfg or load_config()
    destino = pasta / nome
    existente = _ler(destino, COLUNAS)
    ja = set(existente.get("arquivo", pd.Series(dtype=str)).astype(str))

    exportados = _exportacoes(pasta)
    todos = sorted([*pasta.rglob("*.nox"), *exportados])
    novas, novos_arq, infos = [], [], {}
    for arq in todos:
        rel = arq.relative_to(pasta).as_posix()
        if rel in ja or arq.name in ja:
            continue
        linha = {c: "" for c in COLUNAS}
        linha.update({"arquivo": rel, "measurement_id": arq.stem})
        try:
            info, curvas = exportados[arq] if arq in exportados else nox_to_curves(arq)
            infos[arq] = info
        except Exception as e:  # noqa: BLE001
            linha["observacoes"] = f"não foi possível ler: {e}"
            novas.append(linha)
            continue
        if not curvas:
            linha["observacoes"] = "sem curva de potencial x corrente"
        else:
            c = curvas[0]
            linha.update({"tecnica": c["tecnica"], "n_pontos": len(c["potential_v"]),
                          "qc_automatico": _qc_rapido(c, cfg)})
        novas.append(linha)
        novos_arq.append(arq)

    # tudo o que dá para deduzir (amostra, réplica, estágio, data...) já vem preenchido
    infos.update({k: v[0] for k, v in exportados.items()})
    auto = inferir(todos, infos, cfg)
    por_rel = {r["_caminho"].relative_to(pasta).as_posix(): r for _, r in auto.iterrows()} if len(auto) else {}
    # protocolo (etapas e técnica) reconhecido pelos estágios deduzidos
    from .protocolos import ajustar
    from types import SimpleNamespace
    cfg = ajustar(cfg, SimpleNamespace(medicoes=auto.reindex(columns=["sensor_state"]) if len(auto) else None))
    for linha in novas:
        ded = por_rel.get(linha["arquivo"])
        if ded is None:
            continue
        for k in ("sample_id", "replicate_id", "sensor_state", "contamination_status", "target_bacterium",
                  "measurement_date"):
            if k in ded and pd.notna(ded[k]) and not linha.get(k):
                linha[k] = ded[k]
        linha["measurement_id"] = ded.get("measurement_id") or linha["measurement_id"]
        linha["preenchido_auto"] = ded.get("preenchido_auto", "")
        if linha["tecnica"] and linha["tecnica"] != cfg["dados"]["tecnica"]:
            linha["observacoes"] = (linha["observacoes"] + "; " if linha["observacoes"] else "") + \
                f"técnica {linha['tecnica']}: não entra no treino ({cfg['dados']['tecnica']})"

    # linhas antigas: completa só os campos que ficaram em branco (o que a pessoa preencheu fica)
    for col in ("preenchido_auto",):
        if col not in existente:
            existente[col] = ""
    for i, r in existente.iterrows():
        ded = por_rel.get(str(r.get("arquivo", "")).replace("\\", "/"))
        if ded is None:
            ded = next((d for k, d in por_rel.items() if Path(k).name == Path(str(r.get("arquivo", ""))).name), None)
        if ded is None:
            continue
        preenchidos = []
        for k in ("sample_id", "replicate_id", "sensor_state", "contamination_status", "target_bacterium",
                  "measurement_date"):
            vazio = pd.isna(r.get(k)) or str(r.get(k)).strip() == ""
            if vazio and k in ded and pd.notna(ded[k]):
                existente.at[i, k] = str(ded[k])
                preenchidos.append(k)
        if "tecnica" not in existente or pd.isna(r.get("tecnica")) or not str(r.get("tecnica")).strip():
            try:
                _, cv = exportados[ded["_caminho"]] if ded["_caminho"] in exportados \
                    else nox_to_curves(ded["_caminho"])
                if cv:
                    existente.at[i, "tecnica"] = cv[0]["tecnica"]
                    existente.at[i, "n_pontos"] = str(len(cv[0]["potential_v"]))
                    existente.at[i, "qc_automatico"] = _qc_rapido(cv[0], cfg)
            except Exception:  # noqa: BLE001
                pass
        if preenchidos:
            existente.at[i, "preenchido_auto"] = ", ".join(preenchidos)

    tabela = pd.concat([existente, pd.DataFrame(novas, columns=COLUNAS)], ignore_index=True)
    # utf-8-sig: o Excel em português abre com acentos corretos
    tabela.to_csv(destino, index=False, encoding="utf-8-sig")

    # tabela por amostra (rótulo e carga): só acrescenta amostras novas
    estagios = cfg["dados"].get("estagios") or ESTAGIOS_PADRAO
    plan = tabela.replace(r"^\s*$", pd.NA, regex=True)
    if plan["sample_id"].notna().any():
        base_am = plan.dropna(subset=["sample_id"])
        tec = base_am["tecnica"].fillna(cfg["dados"]["tecnica"])
        base_am = base_am[tec == cfg["dados"]["tecnica"]]        # estágios contam só na técnica do treino
        resumo = tabela_amostras(base_am.assign(contamination_status=pd.to_numeric(
            base_am["contamination_status"], errors="coerce")), estagios)
        dest_am = pasta / "amostras.csv"
        am_exist = _ler(dest_am, list(resumo.columns))
        if len(am_exist):
            atual = resumo.set_index("sample_id")
            for col in ("n_arquivos", "n_replicas", "estagios_encontrados", "observacoes"):
                am_exist[col] = am_exist["sample_id"].map(atual[col]).fillna(am_exist.get(col, ""))
            resumo = pd.concat([am_exist, resumo[~resumo["sample_id"].isin(set(am_exist["sample_id"]))]],
                               ignore_index=True)
        resumo.to_csv(dest_am, index=False, encoding="utf-8-sig")
    return destino, len(novas)
