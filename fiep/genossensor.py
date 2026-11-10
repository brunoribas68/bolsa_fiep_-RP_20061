"""Base do genossensor: .nox DPV (branco / alvo / negativo) -> tabela `ensaios` -> pico -> treino.

Fluxo:
    fiep rna importar --entrada dados/rna      # lê os .nox, extrai o pico, liga cada alvo ao seu branco
    fiep rna tabela [--saida rna.xlsx]          # a base pronta (com sinal relativo ao branco)
    fiep rna treinar                            # contaminado x não contaminado + curva de calibração

Nome do arquivo (padrão da equipe): técnica - etapa - concentração (ng/mL) - eletrodo, ex.:
dpv-bare-E1, dpv-tratado-E1, dpv-branco-E1, dpv-RNA-0,1-E1, dpv-RNA-10,0-E1 (e dpv-negativo-E1).
O nome do procedimento no NOVA completa o resto, ex.: "DPV SPCE H2SO4 Oligo 4N RNA 1,5 ng-mL"
(eletrodo impresso, tratamento, elemento de captura). O que faltar ou estiver errado se corrige com um `ensaios.csv` na pasta
(coluna `arquivo` + as colunas a sobrescrever). Dicionário: docs/DICIONARIO_DADOS.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .ingest import sha256_arquivo
from .io.nox import nox_to_curves
from .picos import _pulso

TECNICAS = ("DPV", "SWV", "CV", "EIS")
ELETRODOS = ("SPCE", "SPE", "SPAuE", "GCE", "AuE", "ITO")
TRATAMENTOS = ("H2SO4", "KOH", "NaOH", "PBS", "KCl")
FATOR_NG = {"fg": 1e-6, "pg": 1e-3, "ng": 1.0, "ug": 1e3, "µg": 1e3, "μg": 1e3}
CAMPOS_PICO = ("e_pico_v", "i_pico_ua", "i_base_ua", "altura_ua", "largura_v", "area_uav")
FEATURES = ("altura_ua", "i_pico_ua", "e_pico_v", "largura_v", "area_uav")
MIN_POR_CLASSE = 3


def ler_procedimento(texto: str | None) -> dict:
    """Separa o nome do procedimento do NOVA nos campos da base."""
    t = (texto or "").strip()
    r: dict = {"procedimento": t or None}
    palavras = t.split()
    r["tecnica"] = next((p.upper() for p in palavras if p.upper() in TECNICAS), None)
    r["tipo_eletrodo"] = next((p for p in palavras if p.upper() in {e.upper() for e in ELETRODOS}), None)
    r["tratamento"] = next((p for p in palavras if p.upper() in {x.upper() for x in TRATAMENTOS}), None)
    m = re.search(r"\b(oligo\s*[\w-]+|sonda\s*[\w-]+|probe\s*[\w-]+|aptâmero\s*[\w-]+)", t, re.I)
    r["elemento_captura"] = m.group(1) if m else None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(fg|pg|ng|ug|µg|μg)\s*[-/ ]?\s*m?l\b", t, re.I)
    baixo = t.lower()
    if re.search(r"\bbranco\b|\bblank\b", baixo):
        r["tipo"], r["concentracao"] = "branco", 0.0
    elif re.search(r"\bnegativo\b|\bcontrole\b", baixo):
        r["tipo"], r["concentracao"] = "negativo", 0.0
    elif m:
        r["tipo"] = "alvo"
        r["concentracao"] = float(m.group(1).replace(",", ".")) * FATOR_NG[m.group(2).lower()]
    elif re.search(r"\bbare\b", baixo):
        r["tipo"], r["concentracao"] = "bare", 0.0
    elif re.search(r"\btratad[oa]\b", baixo):
        r["tipo"], r["concentracao"] = "tratado", 0.0
    else:
        r["tipo"], r["concentracao"] = None, None
    r["alvo"] = "RNA" if re.search(r"\brna\b", baixo) or r["tipo"] == "alvo" else None
    r["unidade"] = "ng/mL"
    return r


PADRAO_NOME = re.compile(
    r"^(?P<tecnica>dpv|swv|cv)[-_ ](?P<etapa>bare|tratado|branco|rna|negativo)"
    r"(?:[-_ ](?P<conc>\d+(?:[.,]\d+)?))?[-_ ](?P<eletrodo>E\d+)\b", re.I)


def ler_nome(nome: str) -> dict:
    """Lê o nome do arquivo no padrão técnica-etapa-concentração-eletrodo (vazio se não seguir)."""
    m = PADRAO_NOME.match(Path(nome).stem)
    if not m:
        return {}
    etapa = m["etapa"].lower()
    r = {"tecnica": m["tecnica"].upper(), "eletrodo_id": m["eletrodo"].upper(),
         "tipo": "alvo" if etapa == "rna" else etapa}
    if etapa == "rna":
        r["alvo"] = "RNA"
        if m["conc"]:
            r["concentracao"] = float(m["conc"].replace(",", "."))
            # padrão novo sempre com decimal (0,1 / 10,0); sem decimal é o padrão antigo (15 = 1,5): o
            # procedimento decide
            r["conc_com_decimal"] = bool(re.search(r"[.,]", m["conc"]))
    else:
        r["concentracao"] = 0.0
    return r


def eletrodo_do_nome(nome: str) -> str | None:
    m = re.search(r"(?:^|[-_ .])(E\d+)(?=[-_ .]|$)", Path(nome).stem, re.I)
    return m.group(1).upper() if m else None


def ler_arquivo(path: str | Path) -> dict:
    """Uma linha da base a partir de um .nox (primeira curva de pulso do arquivo)."""
    path = Path(path)
    info, curvas = nox_to_curves(path)
    curva = next((c for c in curvas if c["tecnica"] in ("DPV", "SWV")), curvas[0] if curvas else None)
    r = ler_procedimento(info.get("procedimento"))
    r.update(arquivo=path.name, sha256=sha256_arquivo(path), canal=info.get("instrumento"),
             medido_em=info.get("data_hora_procedimento"), eletrodo_id=eletrodo_do_nome(path.name))
    n = ler_nome(path.name)
    avisos = []
    if n:
        conc_proc = r.get("concentracao")
        com_decimal = n.pop("conc_com_decimal", True)
        if "concentracao" in n and not com_decimal and conc_proc is not None:
            n.pop("concentracao")                   # nome antigo (rna-15): vale o procedimento
        elif (n.get("concentracao") is not None and conc_proc is not None
              and abs(n["concentracao"] - conc_proc) > 1e-9):
            avisos.append(f"concentração no nome ({n['concentracao']:g}) ≠ procedimento ({conc_proc:g}); "
                          "usei a do nome")
        if r.get("tipo") and n["tipo"] != r["tipo"]:
            avisos.append(f"etapa no nome ({n['tipo']}) ≠ procedimento ({r['tipo']}); usei a do nome")
        r.update(n)
        if r["tipo"] in ("bare", "tratado"):
            r["alvo"] = None
            r["elemento_captura"] = None             # ainda sem o elemento de captura
    if avisos:
        r["observacoes"] = "; ".join(avisos)
    if curva is None:
        r["observacoes"] = "sem curva de medição no arquivo"
        return r
    r["tecnica"] = r["tecnica"] or curva["tecnica"]
    e, i = np.asarray(curva["potential_v"], float), np.asarray(curva["current_ua"], float)
    if curva.get("scan_index") and len(set(curva["scan_index"])) > 1:
        ultimo = np.asarray(curva["scan_index"]) == max(curva["scan_index"])
        e, i = e[ultimo], i[ultimo]
    r.update(_pulso(e, i))
    r["potential_v"], r["current_ua"] = e.tolist(), i.tolist()
    return r


def ler_pasta(pasta: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """Todos os .nox da pasta (e subpastas) + correções do ensaios.csv. Devolve (linhas, avisos)."""
    pasta = Path(pasta)
    arquivos = sorted(p for p in pasta.rglob("*") if p.suffix.lower() == ".nox")
    avisos: list[str] = []
    linhas = []
    for a in arquivos:
        try:
            linhas.append(ler_arquivo(a))
        except Exception as ex:                        # arquivo corrompido não para o lote
            avisos.append(f"{a.name}: não foi possível ler ({ex})")
    df = pd.DataFrame(linhas)
    correcoes = pasta / "ensaios.csv"
    if len(df) and correcoes.exists():
        c = pd.read_csv(correcoes, sep=None, engine="python", dtype=str).set_index("arquivo")
        for arq, linha in c.iterrows():
            alvo = df["arquivo"] == arq
            if not alvo.any():
                avisos.append(f"ensaios.csv: {arq} não está na pasta")
                continue
            for col, v in linha.dropna().items():
                df.loc[alvo, col] = float(v.replace(",", ".")) if col == "concentracao" else v
    for _, r in df.iterrows() if len(df) else []:
        if isinstance(r.get("observacoes"), str):
            avisos.append(f"{r['arquivo']}: {r['observacoes']}")
        falta = [c for c in ("eletrodo_id", "tipo") if pd.isna(r.get(c))]
        if r.get("tipo") in ("branco", "alvo", "negativo") and pd.isna(r.get("elemento_captura")):
            falta.append("elemento_captura")
        if falta:
            avisos.append(f"{r['arquivo']}: sem {', '.join(falta)} (corrija no ensaios.csv)")
    return df, avisos


# ----------------------------------------------------------------------------- banco
def importar(s, pasta: str | Path, empresa: str | None = None, conjunto: str | None = None,
             elemento: str | None = None, eletrodo: str | None = None, bacteria: str | None = None) -> dict:
    """Grava os .nox da pasta em `ensaios` (repetido pelo SHA-256 é ignorado) e liga cada alvo ao branco."""
    from sqlalchemy import select
    from .orm import Coleta, Empresa, Ensaio

    df, avisos = ler_pasta(pasta)
    for col, v in (("elemento_captura", elemento), ("eletrodo_id", eletrodo), ("bacteria", bacteria)):
        if v and len(df):
            if col == "elemento_captura":
                df.loc[df["tipo"].isin(["branco", "alvo", "negativo"]), col] = v
            elif col == "eletrodo_id":
                df[col] = df.get(col, pd.Series(index=df.index, dtype=object)).fillna(v)
            else:
                df[col] = v
    ja = set(s.scalars(select(Ensaio.sha256))) if len(df) else set()
    novos = df[~df["sha256"].isin(ja)] if len(df) else df
    n_dup = 0
    if len(novos):
        dup = novos[novos.duplicated("sha256")]
        avisos += [f"{a}: mesmo conteúdo de outro arquivo da pasta (ignorado)" for a in dup["arquivo"]]
        n_dup = len(dup)
        novos = novos.drop_duplicates("sha256")
    ok = novos.dropna(subset=["eletrodo_id", "tipo"]) if len(novos) else novos
    if len(ok):
        precisa = ok["tipo"].isin(["branco", "alvo", "negativo"])
        ok = ok[~precisa | ok["elemento_captura"].notna()]
    emp = None
    if empresa:
        emp = s.scalar(select(Empresa).where(Empresa.nome == empresa)) or Empresa(nome=empresa)
        s.add(emp)
        s.flush()
    coleta = None
    if len(ok):
        coleta = Coleta(empresa_id=emp.id if emp else None, origem=str(pasta), conjunto=conjunto,
                        descricao="ensaios do genossensor", n_medicoes=len(ok))
        s.add(coleta)
        s.flush()
    colunas = {c.name for c in Ensaio.__table__.columns} - {"id", "criado_em", "branco_id"}
    for _, r in ok.iterrows():
        dados = {k: (None if _vazio(v) else v) for k, v in r.items() if k in colunas}
        if isinstance(dados.get("medido_em"), pd.Timestamp):
            dados["medido_em"] = dados["medido_em"].to_pydatetime()
        s.add(Ensaio(**dados, empresa_id=emp.id if emp else None, coleta_id=coleta.id, conjunto=conjunto))
    s.flush()
    ligados = ligar_brancos(s)
    s.commit()
    return {"lidos": len(df), "gravados": len(ok), "repetidos": len(df) - len(novos) - n_dup,
            "sem_dados": len(novos) - len(ok), "ligados_ao_branco": ligados, "avisos": avisos,
            "coleta_id": coleta.id if coleta else None}


def _vazio(v) -> bool:
    if isinstance(v, (list, dict)):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def ligar_brancos(s) -> int:
    """Liga cada alvo/negativo sem branco ao branco do mesmo eletrodo e elemento de captura (o mais
    recente antes da medição; sem data, o mais recente). Devolve quantos foram ligados."""
    from sqlalchemy import select
    from .orm import Ensaio
    brancos = list(s.scalars(select(Ensaio).where(Ensaio.tipo == "branco")))
    n = 0
    for e in s.scalars(select(Ensaio).where(Ensaio.tipo.in_(("alvo", "negativo")), Ensaio.branco_id.is_(None))):
        cand = [b for b in brancos if b.eletrodo_id == e.eletrodo_id and b.elemento_captura == e.elemento_captura
                and b.empresa_id == e.empresa_id]
        if e.medido_em:
            antes = [b for b in cand if b.medido_em and b.medido_em <= e.medido_em]
            cand = antes or cand
        if cand:
            e.branco_id = max(cand, key=lambda b: (b.medido_em is not None, b.medido_em or 0, b.id)).id
            n += 1
    return n


def tabela(s, incluir_curvas: bool = False) -> pd.DataFrame:
    """A base com as colunas derivadas: altura do branco, sinal relativo (%), coerência e rótulo."""
    from .orm import Ensaio
    cols = [c.name for c in Ensaio.__table__.columns if incluir_curvas or c.name not in ("potential_v", "current_ua")]
    df = pd.read_sql_table("ensaios", s.connection(), columns=cols)
    if df.empty:
        return df
    altura = df.set_index("id")["altura_ua"]
    df["altura_branco_ua"] = df["branco_id"].map(altura)
    df.loc[df["tipo"] == "branco", "altura_branco_ua"] = df["altura_ua"]
    # altura de cada etapa do mesmo eletrodo (bare, tratado, branco): qualidade do eletrodo
    for etapa in ("bare", "tratado"):
        h = df[df["tipo"] == etapa].sort_values("id").groupby("eletrodo_id")["altura_ua"].last()
        df[f"altura_{etapa}_ua"] = df["eletrodo_id"].map(h)
    df["sinal_rel_pct"] = 100 * (df["altura_branco_ua"] - df["altura_ua"]) / df["altura_branco_ua"]
    # regra do sensor (signal-off): com o alvo, o pico tem de ficar abaixo do branco
    df["abaixo_do_branco"] = np.where(df["tipo"] == "alvo",
                                      np.where(df["altura_branco_ua"].isna(), None,
                                               df["altura_ua"] < df["altura_branco_ua"]), None)
    df["log10_concentracao"] = np.where(df["concentracao"] > 0, np.log10(df["concentracao"].where(df["concentracao"] > 0)), np.nan)
    return df


def rotular(df: pd.DataFrame, limiar_ng_ml: float = 0.0, branco_como_negativo: bool = True) -> pd.Series:
    """1 = contaminado (alvo acima do limiar); 0 = negativo (e branco, se pedido); NaN = fora do treino."""
    y = pd.Series(np.nan, index=df.index)
    y[(df["tipo"] == "alvo") & (df["concentracao"] > limiar_ng_ml)] = 1
    y[df["tipo"] == "negativo"] = 0
    if branco_como_negativo:
        y[df["tipo"] == "branco"] = 0
    return y


def calibracao(df: pd.DataFrame) -> dict | None:
    """Reta sinal relativo (%) x log10(concentração) nos alvos ligados a um branco."""
    a = df[(df["tipo"] == "alvo") & df["sinal_rel_pct"].notna() & df["log10_concentracao"].notna()]
    if len(a) < 3:
        return None
    x, y = a["log10_concentracao"].to_numpy(float), a["sinal_rel_pct"].to_numpy(float)
    incl, inter = np.polyfit(x, y, 1)
    pred = incl * x + inter
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum() if np.ptp(y) else float("nan")
    out = {"n": int(len(a)), "inclinacao_pct_por_decada": round(float(incl), 3),
           "intercepto_pct": round(float(inter), 3), "r2": round(float(r2), 3)}
    b = df[df["tipo"] == "branco"]["altura_ua"].dropna()
    if len(b) >= 3 and incl > 0:
        # LOD = 3 x desvio dos brancos (em % do branco médio) / inclinação
        dp_rel = 100 * b.std(ddof=1) / b.mean()
        out["lod_ng_ml"] = round(float(10 ** ((3 * dp_rel - inter) / incl)), 4)
    else:
        out["lod_ng_ml"] = None
        out["lod_motivo"] = "precisa de pelo menos 3 brancos (repetições) para o desvio do branco"
    return out


def treinar(df: pd.DataFrame, limiar_ng_ml: float = 0.0, branco_como_negativo: bool = True, seed: int = 0) -> dict:
    """Contaminado x não contaminado só com o pico (validação deixando um eletrodo de fora).

    Usa só medidas do próprio voltamograma (altura, corrente e potencial do pico, largura, área): o sinal
    relativo ao branco é 0 por definição nos brancos e vazaria o rótulo."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix
    from sklearn.model_selection import LeaveOneGroupOut, LeaveOneOut
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    d = df[df["qc_flag"].fillna("PASS") != "FAIL"].copy()
    d["y"] = rotular(d, limiar_ng_ml, branco_como_negativo)
    d = d.dropna(subset=["y", *FEATURES])
    contagem = d["y"].value_counts().reindex([0.0, 1.0], fill_value=0)
    r = {"n": int(len(d)), "nao_contaminado": int(contagem[0.0]), "contaminado": int(contagem[1.0]),
         "limiar_ng_ml": limiar_ng_ml, "branco_como_negativo": branco_como_negativo,
         "features": list(FEATURES), "calibracao": calibracao(df)}
    if contagem.min() < MIN_POR_CLASSE:
        r["status"] = "dados insuficientes"
        r["motivo"] = (f"precisa de pelo menos {MIN_POR_CLASSE} medições de cada classe; hoje há "
                       f"{r['nao_contaminado']} não contaminado(s) e {r['contaminado']} contaminado(s)")
        return r
    X, y = d[list(FEATURES)].to_numpy(float), d["y"].to_numpy(int)
    grupos = d["eletrodo_id"].astype(str).to_numpy()
    cv = LeaveOneGroupOut() if len(set(grupos)) >= 3 else LeaveOneOut()
    prev = np.empty(len(y), dtype=int)
    for tr, te in cv.split(X, y, grupos):
        if len(set(y[tr])) < 2:
            prev[te] = y[tr][0]
            continue
        m = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000))
        prev[te] = m.fit(X[tr], y[tr]).predict(X[te])
    r.update(status="ok", validacao="deixa um eletrodo de fora" if isinstance(cv, LeaveOneGroupOut) else "deixa uma medição de fora",
             balanced_accuracy=round(float(balanced_accuracy_score(y, prev)), 3),
             matriz_confusao=confusion_matrix(y, prev, labels=[0, 1]).tolist())
    return r
