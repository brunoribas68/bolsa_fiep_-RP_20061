"""Ensaios do genossensor: .nox DPV (branco ou RNA) -> tabela `ensaios` com o pico e a curva.

    fiep rna pastas --entrada dados/rna     # cria contaminado/ (RNA) e nao_contaminado/ (branco)
    fiep rna importar --entrada dados/rna   # lê os .nox, mede o pico, liga cada RNA ao branco do eletrodo
    fiep rna tabela [--saida base.xlsx]     # a base pronta

Nome do arquivo (padrão da equipe): técnica - etapa - concentração (ng/mL) - eletrodo:
`dpv-branco-E1.nox` e `dpv-RNA-0,1-E1.nox`. O procedimento do NOVA completa o resto, ex.:
"DPV SPCE H2SO4 Oligo 4N RNA 1,5 ng-mL" (eletrodo impresso, tratamento, elemento de captura).
Correções: um `ensaios.csv` na pasta (coluna `arquivo` + as colunas a sobrescrever).
Dicionário: docs/DICIONARIO_DADOS.md.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .io.nox import nox_to_curves
from .pico import medir_pico

TECNICAS = ("DPV", "SWV", "CV", "EIS")
ELETRODOS = ("SPCE", "SPE", "SPAuE", "GCE", "AuE", "ITO")
TRATAMENTOS = ("H2SO4", "KOH", "NaOH", "PBS", "KCl")
FATOR_NG = {"fg": 1e-6, "pg": 1e-3, "ng": 1.0, "ug": 1e3, "µg": 1e3, "μg": 1e3}
PASTAS = {"contaminado": "rna", "nao_contaminado": "branco"}       # pasta -> o único tipo que ela aceita
PADRAO_NOME = re.compile(
    r"^(?P<tecnica>dpv|swv|cv)[-_ ](?P<etapa>[a-z]+)(?:[-_ ](?P<conc>\d+(?:[.,]\d+)?))?[-_ ](?P<eletrodo>E\d+)\b",
    re.I)


def sha256_arquivo(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ler_procedimento(texto: str | None) -> dict:
    """Separa o nome do procedimento do NOVA nos campos da base."""
    t = (texto or "").strip()
    palavras = t.split()
    r: dict = {"procedimento": t or None,
               "tecnica": next((p.upper() for p in palavras if p.upper() in TECNICAS), None),
               "tipo_eletrodo": next((p for p in palavras if p.upper() in {e.upper() for e in ELETRODOS}), None),
               "tratamento": next((p for p in palavras if p.upper() in {x.upper() for x in TRATAMENTOS}), None)}
    m = re.search(r"\b(oligo\s*[\w-]+|sonda\s*[\w-]+|probe\s*[\w-]+|aptâmero\s*[\w-]+)", t, re.I)
    r["elemento_captura"] = m.group(1) if m else None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(fg|pg|ng|ug|µg|μg)\s*[-/ ]?\s*m?l\b", t, re.I)
    if re.search(r"\bbranco\b|\bblank\b", t, re.I):
        r["tipo"], r["concentracao"] = "branco", 0.0
    elif m:
        r["tipo"] = "rna"
        r["concentracao"] = float(m.group(1).replace(",", ".")) * FATOR_NG[m.group(2).lower()]
    else:
        r["tipo"], r["concentracao"] = None, None
    return r


def ler_nome(nome: str) -> dict:
    """Lê o nome no padrão técnica-etapa-concentração-eletrodo (vazio se não seguir).

    A etapa vem como está (`branco`, `rna`, ou outra que a base não usa, ex.: `bare`); quem chama decide."""
    m = PADRAO_NOME.match(Path(nome).stem)
    if not m:
        return {}
    r = {"tecnica": m["tecnica"].upper(), "eletrodo_id": m["eletrodo"].upper(), "tipo": m["etapa"].lower()}
    if r["tipo"] == "branco":
        r["concentracao"] = 0.0
    elif r["tipo"] == "rna" and m["conc"]:
        r["concentracao"] = float(m["conc"].replace(",", "."))
        # padrão da equipe sempre com decimal (0,1 / 10,0); sem decimal é o padrão antigo (rna-15 = 1,5):
        # aí vale o procedimento
        r["conc_com_decimal"] = bool(re.search(r"[.,]", m["conc"]))
    return r


def eletrodo_do_nome(nome: str) -> str | None:
    m = re.search(r"(?:^|[-_ .])(E\d+)(?=[-_ .]|$)", Path(nome).stem, re.I)
    return m.group(1).upper() if m else None


def ler_curva(path: str | Path) -> tuple[dict, np.ndarray, np.ndarray]:
    """(informações do .nox, potencial em V, corrente em µA) da curva DPV/SWV do arquivo (último scan)."""
    info, curvas = nox_to_curves(Path(path))
    curva = next((c for c in curvas if c["tecnica"] in ("DPV", "SWV")), curvas[0] if curvas else None)
    if curva is None:
        raise ValueError("sem curva de medição no arquivo")
    e, i = np.asarray(curva["potential_v"], float), np.asarray(curva["current_ua"], float)
    if curva.get("scan_index") and len(set(curva["scan_index"])) > 1:
        ultimo = np.asarray(curva["scan_index"]) == max(curva["scan_index"])
        e, i = e[ultimo], i[ultimo]
    return {**info, "tecnica": curva["tecnica"]}, e, i


def ler_arquivo(path: str | Path) -> dict:
    """Uma linha da base a partir de um .nox (`_erro` diz se ela pode entrar)."""
    path = Path(path)
    info, e, i = ler_curva(path)
    r = ler_procedimento(info.get("procedimento"))
    r.update(arquivo=path.name, sha256=sha256_arquivo(path), canal=info.get("instrumento"),
             medido_em=info.get("data_hora_procedimento"), eletrodo_id=eletrodo_do_nome(path.name))
    avisos, n = [], ler_nome(path.name)
    if n:
        conc_proc = r.get("concentracao")
        if n.pop("conc_com_decimal", True) is False and conc_proc is not None:
            n.pop("concentracao")                   # nome antigo (rna-15): vale o procedimento
        elif n.get("concentracao") is not None and conc_proc is not None and abs(n["concentracao"] - conc_proc) > 1e-9:
            avisos.append(f"concentração no nome ({n['concentracao']:g}) ≠ procedimento ({conc_proc:g}); usei a do nome")
        if r.get("tipo") and n["tipo"] != r["tipo"]:
            avisos.append(f"etapa no nome ({n['tipo']}) ≠ procedimento ({r['tipo']}); usei a do nome")
        r.update(n)
    r["tecnica"] = r["tecnica"] or info["tecnica"]
    r.update(medir_pico(e, i))
    r["potential_v"], r["current_ua"] = e.tolist(), i.tolist()
    if avisos:
        r["observacoes"] = "; ".join(avisos)
    return r


def _erro(r: dict) -> str | None:
    r = {k: (None if not isinstance(v, (list, dict)) and _vazio(v) else v) for k, v in r.items()}
    if r.get("tipo") not in ("branco", "rna"):
        etapa = r.get("tipo")
        return (f"etapa '{etapa}' não entra na base (só branco e RNA)" if etapa
                else "não deu para saber se é branco ou RNA (nome do arquivo ou procedimento)")
    if r["tipo"] == "rna" and not r.get("concentracao"):
        return "RNA sem concentração (nome dpv-RNA-<conc>-Ej ou procedimento '… RNA <conc> ng-mL')"
    if not r.get("eletrodo_id"):
        return "sem o eletrodo no nome do arquivo (…-E1.nox)"
    if len(r.get("potential_v") or []) < 20:
        return "curva com menos de 20 pontos"
    return None


def criar_pastas(pasta: str | Path) -> list[Path]:
    """Cria contaminado/ e nao_contaminado/ dentro da pasta (as que já existem ficam como estão)."""
    criadas = [Path(pasta) / p for p in PASTAS]
    for p in criadas:
        p.mkdir(parents=True, exist_ok=True)
    return criadas


def pasta_do_arquivo(arquivo: Path, raiz: Path) -> str | None:
    """'contaminado' ou 'nao_contaminado' se o arquivo estiver numa dessas pastas (a mais interna vale)."""
    for parte in reversed(arquivo.parent.relative_to(raiz).parts):
        chave = re.sub(r"[\s-]+", "_", parte.lower()).replace("não", "nao")
        if chave in PASTAS:
            return chave
    return None


def conferir_pasta(pasta: str | None, tipo: str | None) -> str | None:
    """Erro quando a pasta e o arquivo discordam (None = tudo certo ou fora das pastas)."""
    if pasta and tipo in ("branco", "rna") and PASTAS[pasta] != tipo:
        return f"é {tipo} mas está em {pasta}/ (contaminado/ só recebe RNA; nao_contaminado/ só branco)"
    return None


def ler_pasta(pasta: str | Path, padrao: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Todos os .nox da pasta (e subpastas) + `padrao` (valor de um campo para quem não tem) + correções do
    ensaios.csv. Devolve (linhas, avisos); a coluna `erro` diz por que uma linha não entra."""
    pasta = Path(pasta)
    avisos: list[str] = []
    linhas = []
    for a in sorted(p for p in pasta.rglob("*") if p.suffix.lower() == ".nox"):
        try:
            linhas.append({**ler_arquivo(a), "pasta": pasta_do_arquivo(a, pasta)})
        except Exception as ex:                        # arquivo corrompido não para o lote
            avisos.append(f"{a.name}: não foi possível ler ({ex}) — não gravado")
    df = pd.DataFrame(linhas)
    for col, v in (padrao or {}).items():
        if v and len(df):
            df[col] = df[col].fillna(v) if col in df else v
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
    if len(df):
        df["erro"] = [_erro(r) or conferir_pasta(r["pasta"] if isinstance(r["pasta"], str) else None, r["tipo"])
                      for r in df.to_dict("records")]
        for r in df.itertuples():
            if isinstance(r.erro, str):
                avisos.append(f"{r.arquivo}: {r.erro} — não gravado")
            elif isinstance(getattr(r, "observacoes", None), str):
                avisos.append(f"{r.arquivo}: {r.observacoes}")
    return df, avisos


# ----------------------------------------------------------------------------- banco
def importar(s, pasta: str | Path, empresa: str | None = None, empresa_id: int | None = None, coleta=None,
             elemento: str | None = None, eletrodo: str | None = None, bacteria: str | None = None,
             usuario_id: int | None = None) -> dict:
    """Grava os .nox da pasta em `ensaios` (o mesmo arquivo de novo é ignorado pelo SHA-256) e liga cada
    RNA ao branco do mesmo eletrodo. `coleta`: a coleta já criada (plataforma); sem ela, cria uma."""
    from sqlalchemy import select
    from .orm import Coleta, Empresa, Ensaio

    df, avisos = ler_pasta(pasta, {"elemento_captura": elemento, "eletrodo_id": eletrodo, "bacteria": bacteria})
    ja = set(s.scalars(select(Ensaio.sha256))) if len(df) else set()
    novos = df[~df["sha256"].isin(ja)] if len(df) else df
    ok = novos[novos["erro"].isna()].drop_duplicates("sha256") if len(novos) else novos
    if empresa and empresa_id is None:
        emp = s.scalar(select(Empresa).where(Empresa.nome == empresa)) or Empresa(nome=empresa)
        s.add(emp)
        s.flush()
        empresa_id = emp.id
    if coleta is None and len(ok):
        coleta = Coleta(empresa_id=empresa_id, origem=str(pasta), descricao="ensaios do genossensor",
                        criado_por_id=usuario_id)
        s.add(coleta)
        s.flush()
    colunas = {c.name for c in Ensaio.__table__.columns} - {"id", "criado_em", "branco_id", "empresa_id", "coleta_id"}
    for r in ok.to_dict("records"):
        dados = {k: v for k, v in r.items() if k in colunas and not _vazio(v)}
        if isinstance(dados.get("medido_em"), pd.Timestamp):
            dados["medido_em"] = dados["medido_em"].to_pydatetime()
        s.add(Ensaio(**dados, empresa_id=empresa_id, coleta_id=coleta.id))
    if coleta is not None:
        coleta.n_ensaios = (coleta.n_ensaios or 0) + len(ok)
        coleta.avisos = avisos
    s.flush()
    ligados = ligar_brancos(s)
    s.commit()
    return {"lidos": len(df), "gravados": len(ok), "ja_no_banco": len(df) - len(novos),
            "nao_gravados": len(novos) - len(ok), "ligados_ao_branco": ligados, "avisos": avisos,
            "coleta_id": coleta.id if coleta is not None else None}


def _vazio(v) -> bool:
    if isinstance(v, (list, dict)):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def ligar_brancos(s) -> int:
    """Liga cada RNA sem branco ao branco do mesmo eletrodo, elemento de captura e empresa (o mais recente
    antes da medição; sem data, o mais recente). Devolve quantos foram ligados."""
    from sqlalchemy import select
    from .orm import Ensaio
    brancos = list(s.scalars(select(Ensaio).where(Ensaio.tipo == "branco")))
    n = 0
    for e in s.scalars(select(Ensaio).where(Ensaio.tipo == "rna", Ensaio.branco_id.is_(None))):
        cand = [b for b in brancos if b.eletrodo_id == e.eletrodo_id and b.elemento_captura == e.elemento_captura
                and b.empresa_id == e.empresa_id]
        if e.medido_em:
            cand = [b for b in cand if b.medido_em and b.medido_em <= e.medido_em] or cand
        if cand:
            e.branco_id = max(cand, key=lambda b: (b.medido_em is not None, b.medido_em or 0, b.id)).id
            n += 1
    return n


def tabela(s, incluir_curvas: bool = False, empresa_id: int | None = None, coleta_id: int | None = None) -> pd.DataFrame:
    """A base com as colunas derivadas: altura do branco ligado, queda do pico (%) e se ficou abaixo do branco."""
    from .orm import Ensaio
    cols = [c.name for c in Ensaio.__table__.columns if incluir_curvas or c.name not in ("potential_v", "current_ua")]
    df = pd.read_sql_table("ensaios", s.connection(), columns=cols)
    if df.empty:
        return df
    altura = df.set_index("id")["altura_ua"]
    df["altura_branco_ua"] = df["branco_id"].map(altura)
    df.loc[df["tipo"] == "branco", "altura_branco_ua"] = df["altura_ua"]
    df["queda_pct"] = 100 * (df["altura_branco_ua"] - df["altura_ua"]) / df["altura_branco_ua"]
    # o sensor é signal-off: com o RNA, o pico tem de ficar abaixo do branco
    df["abaixo_do_branco"] = np.where((df["tipo"] == "rna") & df["altura_branco_ua"].notna(),
                                      df["altura_ua"] < df["altura_branco_ua"], None)
    if empresa_id is not None:
        df = df[df["empresa_id"] == empresa_id]
    if coleta_id is not None:
        df = df[df["coleta_id"] == coleta_id]
    return df.reset_index(drop=True)


def calibracao(df: pd.DataFrame) -> dict | None:
    """Reta queda do pico (%) x log10(concentração) nos RNA ligados a um branco."""
    a = df[(df["tipo"] == "rna") & df["queda_pct"].notna() & (df["concentracao"] > 0)]
    if len(a) < 3 or a["concentracao"].nunique() < 2:
        return None
    x, y = np.log10(a["concentracao"].to_numpy(float)), a["queda_pct"].to_numpy(float)
    incl, inter = np.polyfit(x, y, 1)
    pred = incl * x + inter
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum() if np.ptp(y) else float("nan")
    out = {"n": int(len(a)), "inclinacao_pct_por_decada": round(float(incl), 3),
           "intercepto_pct": round(float(inter), 3), "r2": round(float(r2), 3)}
    b = df[df["tipo"] == "branco"]["altura_ua"].dropna()
    if len(b) >= 3 and incl > 0:
        dp_rel = 100 * b.std(ddof=1) / b.mean()        # LOD = 3 x desvio dos brancos / inclinação
        out["lod_ng_ml"] = round(float(10 ** ((3 * dp_rel - inter) / incl)), 4)
    else:
        out["lod_ng_ml"] = None
        out["lod_motivo"] = "precisa de pelo menos 3 brancos e queda que cresce com a concentração"
    return out
