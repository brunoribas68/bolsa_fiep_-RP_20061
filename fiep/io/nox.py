"""Leitura de arquivos .nox (Metrohm Autolab NOVA 2.x).

`read_nox(path)` devolve os sinais de cada comando de medição com os nomes que o NOVA
mostra (ex.: "Potential applied (V)", "WE(1).δ.Current (A)"), resultados de análise
salvos no arquivo, parâmetros do procedimento e indicadores de qualidade.

`nox_to_curves(path)` converte para o formato canônico da pipeline
(potential_v, current_ua, scan_index), escolhendo o sinal certo para cada técnica.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from .nrbf import Arr, Obj, Ref, read_all


def _short(k):
    return k.rsplit('+', 1)[-1]


class _Graph:
    def __init__(self, objs):
        self.o = objs

    def R(self, x):
        return self.o.get(x.id, x) if isinstance(x, Ref) else x

    def f(self, obj, name):
        """Campo pelo nome curto (ignora o prefixo 'Classe+')."""
        for k, v in obj.fields.items():
            if _short(k) == name:
                return self.R(v)
        return None

    def numeric_list(self, x):
        """Resolve List<T> / T[] -> (array_id, valores) se for numérico."""
        x = self.R(x)
        if isinstance(x, Obj) and '_items' in x.fields:
            arr = self.R(x.fields['_items']); n = x.fields.get('_size') or 0
            if isinstance(arr, Arr):
                vals = arr.items[:n]
                return arr.id, vals
        if isinstance(x, Arr):
            return x.id, x.items
        return None

    def label(self, cmd):
        if not isinstance(cmd, Obj):
            return ''
        for k in ('_text', '_localizedText', '_name'):
            v = self.f(cmd, k)
            if isinstance(v, str) and v:
                return v
        return cmd.cls.rsplit('.', 1)[-1]


def _isnum(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _ticks_to_dt(t):
    if not isinstance(t, int) or t == 0:
        return None
    try:
        return datetime.datetime(1, 1, 1) + datetime.timedelta(microseconds=(t & ((1 << 62) - 1)) // 10)
    except OverflowError:
        return None


def read_nox(path, incluir_brutos=False):
    """
    Lê qualquer .nox do NOVA 2.x.
    Retorna dict com:
      info       – metadados do procedimento
      parametros – lista de dicts (comando, parametro, valor, unidade)
      medicoes   – lista de (nome, DataFrame) com os sinais de cada comando de medição
                   (+ resultados de análise, ex. correção de linha de base, como colunas extras)
    """
    import pandas as pd
    data = Path(path).read_bytes()
    lidos = read_all(data)
    streams = [o for _, o, _ in lidos if isinstance(o, dict) and o]
    if not streams:
        raise ValueError('arquivo não reconhecido como .nox do NOVA')
    completo = max(fim for _, _, fim in lidos) >= len(data)
    G = _Graph(max(streams, key=len))

    info = {'arquivo': Path(path).name}
    for st in streams:
        for o in st.values():
            if isinstance(o, Obj) and o.cls.endswith('ProcedureDescription'):
                info.setdefault('procedimento', o.fields.get('_text'))
                info.setdefault('instrumento', o.fields.get('_instrument'))
                info.setdefault('data_hora_procedimento', _ticks_to_dt(o.fields.get('_timeStamp')))
                info.setdefault('observacoes', o.fields.get('_remarks') if isinstance(o.fields.get('_remarks'), str) else None)

    # --- percorre todos os "parâmetros de comando" do procedimento ---------------
    sinais = {}       # id do comando -> {'nome':..., 'cols': {nome_coluna: (array_id, valores)}}
    analises = {}     # idem, para SignalSetCommand (gráficos/resultados de análise)
    parametros = []
    for o in G.o.values():
        if not isinstance(o, Obj) or '_parameter' not in o.fields:
            continue
        nome = G.f(o, '_name'); texto = G.f(o, '_text'); unid = G.f(o, '_unit')
        nome = nome if isinstance(nome, str) else ''
        texto = texto if isinstance(texto, str) and texto else nome
        unid = unid if isinstance(unid, str) else ''
        pai = G.f(o, '_parent')
        p = G.R(o.fields['_parameter'])
        if p is None:                       # parâmetros do hardware (ex.: vértices do CV)
            hp = G.f(o, '_hParameter')
            p = G.f(hp, '_innerIParameter') if isinstance(hp, Obj) else None
        valor = G.R(p.fields.get('_value')) if isinstance(p, Obj) else p

        lst = G.numeric_list(valor) if valor is not None else None
        if lst is not None:
            aid, vals = lst
            if not vals:
                continue
            # listas de listas (ex.: vários scans) -> uma coluna por sub-lista
            sub = [G.numeric_list(v) for v in vals] if isinstance(vals[0], (Ref, Obj, Arr)) else None
            if sub and all(s is not None for s in sub):
                series = [(f'{texto} [{i + 1}]', s) for i, s in enumerate(sub)]
            elif all(_isnum(v) or v is None for v in vals[:50]):
                series = [(texto, (aid, vals))]
            else:
                continue
            # sinais brutos internos (o NOVA não mostra): marcados com "!" ou "Raw..."
            oculto = '!' in texto or bool(re.search(r'(^|\.)Raw', texto))
            if oculto and not incluir_brutos:
                continue
            alvo = analises if (isinstance(pai, Obj) and pai.cls.endswith('SignalSetCommand')) else sinais
            pid = pai.id if isinstance(pai, Obj) else 0
            if pid not in alvo:
                lab = G.label(pai)
                if alvo is analises:
                    avo = G.f(pai, '_parent')
                    la = G.label(avo)
                    lab = f'{la} – {lab}' if la and la != lab else lab
                alvo[pid] = {'nome': lab or 'Medição', 'cols': {}}
            for t, s in series:
                col = f'{t} ({unid})' if unid else t
                alvo[pid]['cols'].setdefault(col, s)
        elif _isnum(valor) or (isinstance(valor, str) and valor and len(valor) < 200):
            if nome:
                parametros.append({'comando': G.label(pai), 'parametro': texto or nome,
                                   'valor': valor, 'unidade': unid})

    def frame(cols):
        n = max(len(v) for _, v in cols.values())
        return pd.DataFrame({k: list(v) + [None] * (n - len(v)) for k, (_, v) in cols.items()})

    medicoes = []
    tabelas = {}
    ids_por_tabela = {}
    # comandos que reaproveitam o mesmo eixo (ex.: ajuste/linha de base sobre a medição)
    # viram colunas extras da tabela de origem, sem repetir colunas idênticas
    for pid, g in sinais.items():
        if not g['cols']:
            continue
        aids = {aid for aid, _ in g['cols'].values()}
        n = max(len(v) for _, v in g['cols'].values())
        destino = next((d for d, ids in ids_por_tabela.items() if aids & ids), None)
        if destino is None:
            g['orig'] = set(g['cols']); tabelas[pid] = g; ids_por_tabela[pid] = set(aids)
            continue
        for k, v in g['cols'].items():
            if v[0] not in ids_por_tabela[destino]:
                kk = k if k not in tabelas[destino]['cols'] else f'{g["nome"]}: {k}'
                tabelas[destino]['cols'][kk] = v; ids_por_tabela[destino].add(v[0])

    # resultados de análise: colunas novas vão para a tabela da medição de origem
    extras = []
    for g in analises.values():
        cols = g['cols']
        if not cols:
            continue
        aids = {aid for aid, _ in cols.values()}
        destino = next((pid for pid, ids in ids_por_tabela.items() if aids & ids), None)
        novos = {k: v for k, v in cols.items() if v[0] not in (ids_por_tabela.get(destino) or set())}
        if not novos:
            continue
        if destino is not None:
            n = max(len(v) for _, v in tabelas[destino]['cols'].values())
            for k, v in novos.items():
                tabelas[destino]['cols'].setdefault(f'{g["nome"]}: {k}', v)
                ids_por_tabela[destino].add(v[0])
        else:
            extras.append((g['nome'], novos))

    def separar(nome, cols, orig=()):
        """Colunas de tamanhos diferentes (ex.: curva x lista de picos) viram tabelas separadas."""
        por_n = {}
        for k, v in cols.items():
            por_n.setdefault(len(v[1]), {})[k] = v
        ordem = sorted(por_n, key=lambda n: (-len(por_n[n]) if n > 1 else 0, -n))
        ordem.sort(key=lambda n: -n)            # a maior (a curva) primeiro
        saida = []
        for i, n in enumerate(ordem):
            cols_n = por_n[n]
            if i == 0:
                df0 = frame(cols_n)
                df0.attrs['medidas'] = [k for k in cols_n if k in orig]
                saida.append((nome, df0)); continue
            # nome da sub-tabela = comando de análise que a gerou (prefixo "Comando: ")
            pref = next((k.split(': ', 1)[0] for k in cols_n if ': ' in k), None)
            sub = pref.split(' – ')[0] if pref else f'resultados {i}'
            if pref:
                cols_n = {(k.split(': ', 1)[1] if k.startswith(pref + ': ') else k): v for k, v in cols_n.items()}
            saida.append((f'{nome} – {sub}', frame(cols_n)))
        return saida

    for g in tabelas.values():
        medicoes += separar(g['nome'], g['cols'], g.get('orig', ()))
    for nome, cols in extras:
        medicoes += separar(nome, cols)

    info['leitura'] = 'completa' if completo else 'PARCIAL (arquivo corrompido ou incompleto?)'
    info['n_medicoes'] = len(medicoes)
    info['n_pontos'] = ', '.join(str(len(df)) for _, df in medicoes)
    _qualidade(info, medicoes)
    vistos, unicos = set(), []
    for d in parametros:
        k = tuple(d.values())
        if k not in vistos:
            vistos.add(k); unicos.append(d)
    return {'info': info, 'parametros': unicos, 'medicoes': medicoes}


_PARTE = re.compile(r'^(?P<we>WE\(\d+\)\.)?(?:(?P<parte>[^.()]+)\.)?(?P<q>Time|Potential applied|Potential) \(')


def estilo_nova(df):
    """Mesmas colunas que o NOVA mostra/exporta por padrão na tabela de dados:
    Index, Potential applied, só o 1º Time e o 1º WE(1).Potential de cada medição
    (ex.: Forward/Base) e todas as correntes e demais sinais."""
    medidas = df.attrs.get('medidas') or list(df.columns)
    grupos = {}
    for col in medidas:
        m = _PARTE.match(col)
        if m:
            grupos.setdefault((m['we'], m['q']), []).append((col, m['parte']))
    fora = set()
    for membros in grupos.values():
        sem_parte = [c for c, parte in membros if not parte]
        manter = sem_parte[:1] or [membros[0][0]]
        fora |= {c for c, _ in membros if c not in manter}
    cols = [c for c in medidas if c not in fora]
    if 'Index' in cols:
        cols.remove('Index'); cols.insert(0, 'Index')
    return df[cols]


def _qualidade(info, medicoes):
    """Indicadores simples, quando existirem as colunas de potencial e corrente."""
    for _, df in medicoes:
        cols = list(df.columns)
        ea = next((c for c in cols if c.startswith('Potential applied')), None)
        em = next((c for c in cols if re.match(r'WE\(1\)\.(Base\.)?Potential', c)), None)
        ic = next((c for c in cols if re.match(r'WE\(1\)\.(Base\.)?Current', c)), None)
        if ea and em:
            dev = (pd_to_num(df[ea]) - pd_to_num(df[em])).abs()
            info['% pontos E medido ≠ E aplicado (>20 mV)'] = round(100 * float((dev > 0.020).mean()), 1)
        if ic:
            info['|I| máx (A)'] = float(pd_to_num(df[ic]).abs().max())
        if ea or ic:
            break


def pd_to_num(s):
    import pandas as pd
    return pd.to_numeric(s, errors='coerce')



# =====================================================================
#  Saída
# =====================================================================


# ---------------------------------------------------------------------------
# Conversão para o formato canônico da pipeline
# ---------------------------------------------------------------------------
# Para cada técnica, qual coluna é o eixo x (potencial) e qual é a resposta (corrente).
# A ordem importa: a primeira combinação encontrada na tabela é usada.
_SINAL_POR_TECNICA = [
    # DPV / SWV: corrente diferencial (δ) vs potencial aplicado
    ("Potential applied (V)", "WE(1).δ.Current (A)"),
    # CV / LSV: corrente vs potencial aplicado
    ("Potential applied (V)", "WE(1).Current (A)"),
]

_TECNICAS = [
    (re.compile(r"square\s*wave|swv", re.I), "SWV"),
    (re.compile(r"differential|dpv", re.I), "DPV"),
    (re.compile(r"\bcv\b|cyclic|staircase", re.I), "CV"),
    (re.compile(r"linear|lsv", re.I), "LSV"),
]


def detectar_tecnica(nome_comando: str) -> str:
    for rx, tec in _TECNICAS:
        if rx.search(nome_comando or ""):
            return tec
    return "OUTRA"


def curva_de_tabela(df, tecnica: str, comando: str = ""):
    """Curva canônica a partir de uma tabela com as colunas do NOVA (do .nox ou exportada para Excel/CSV)."""
    cols = set(df.columns)
    par = next(((x, y) for x, y in _SINAL_POR_TECNICA if x in cols and y in cols), None)
    if par is None:
        return None
    x, y = par
    e_med = next((c for c in df.columns if re.match(r"WE\(1\)\.(Base\.|Forward\.)?Potential \(V\)$", str(c))), None)
    i_bruta = next((c for c in df.columns if re.match(r"WE\(1\)\.(Base\.|Forward\.)?Current \(A\)$", str(c))), None)
    d = df.copy()
    for col in [x, y, e_med, i_bruta, "Scan"]:
        if col in d:
            d[col] = pd_to_num(d[col])
    d = d.dropna(subset=[x, y])
    if d.empty:
        return None
    return {
        "tecnica": tecnica,
        "comando": comando,
        "potential_v": d[x].tolist(),
        "current_ua": (d[y] * 1e6).tolist(),
        "scan_index": d["Scan"].astype(int).tolist() if "Scan" in d else [1] * len(d),
        "e_medido_v": d[e_med].tolist() if e_med else None,
        # corrente bruta (base/forward): detecta sobrecarga que a corrente diferencial esconde
        "i_bruta_ua": (d[i_bruta] * 1e6).tolist() if i_bruta else None,
    }


def nox_to_curves(path, incluir_brutos: bool = False):
    """Converte um .nox em uma lista de curvas no formato canônico.

    Retorna (info, curvas), onde cada curva é um dict com:
      tecnica, comando, potential_v (lista), current_ua (lista), scan_index (lista),
      e_medido_v (lista ou None) — potencial medido no eletrodo, usado no controle de qualidade,
      i_bruta_ua (lista ou None) — corrente de base/forward, usada para detectar sobrecarga.
    Correntes são convertidas de A para µA, a mesma unidade dos dados do case.
    """
    res = read_nox(path, incluir_brutos)
    curvas = []
    for nome, df in res["medicoes"]:
        if not df.attrs.get("medidas"):
            continue                              # tabelas de análise (picos, ajustes) ficam de fora
        cv = curva_de_tabela(df, detectar_tecnica(nome), nome)
        if cv:
            curvas.append(cv)
    return res["info"], curvas



# =====================================================================
#  Exportações do NOVA (Excel/CSV): mesmas colunas, sem o .nox
# =====================================================================

def eh_exportacao_nova(colunas) -> bool:
    cols = {str(c).strip() for c in colunas}
    return any(x in cols and y in cols for x, y in _SINAL_POR_TECNICA)


def _tecnica_por_nome(nome: str, cols) -> str:
    n = nome.lower()
    for rx, tec in [(r"swv|square", "SWV"), (r"dpv|differential", "DPV"), (r"(^|[^a-z])(cv|cyclic)([^a-z]|$)", "CV"),
                    (r"lsv|linear", "LSV")]:
        if re.search(rx, n):
            return tec
    cols = {str(c) for c in cols}
    if any(".Backward." in c or c.startswith("Backward.") for c in cols):
        return "SWV"                       # onda quadrada: correntes forward/backward
    return "DPV" if "WE(1).δ.Current (A)" in cols else "CV"


def _ler_csv_nova(path):
    import pandas as pd
    for enc in ("utf-8-sig", "cp1252"):
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    # CSV do Excel em português: vírgula decimal
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            conv = pd.to_numeric(df[col].astype(str).str.replace(".", "", regex=False)
                                 .str.replace(",", ".", regex=False), errors="coerce")
            if conv.notna().mean() > 0.9 and pd.to_numeric(df[col], errors="coerce").notna().mean() < 0.5:
                df[col] = conv
    return df


def exportacao_to_curves(path):
    """Lê um Excel/CSV exportado pelo NOVA (ou por `fiep excel`). Devolve [(nome, info, curva)],
    uma por planilha/aba que tenha potencial aplicado x corrente."""
    import pandas as pd
    from pathlib import Path
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        abas = pd.read_excel(path, sheet_name=None)
    else:
        abas = {path.stem: _ler_csv_nova(path)}
    abas = {k: v.rename(columns=lambda c: str(c).strip()) for k, v in abas.items()}
    validas = {k: v for k, v in abas.items() if eh_exportacao_nova(v.columns)
               and str(k).strip().lower() not in {"todos", "todas", "all", "info", "parametros"}}
    info_aba = next((v for k, v in abas.items() if str(k).lower() == "info" and "arquivo" in v), None)
    saida = []
    for aba, df in validas.items():
        nome = path.stem if len(validas) == 1 else f"{path.stem}_{aba}"
        info = {"arquivo": path.name}
        if info_aba is not None:              # Excel do `fiep excel --juntar`: aba Info com o cabeçalho de cada .nox
            stems = info_aba["arquivo"].astype(str).map(lambda s: Path(s).stem)
            aba_s = str(aba).strip()
            linha = info_aba[(stems == aba_s) | stems.str.endswith("_" + aba_s)]
            if len(linha) != 1 and len(validas) == 1 and len(info_aba) == 1:
                linha = info_aba
            if len(linha) == 1:
                info.update({k: v for k, v in linha.iloc[0].items() if pd.notna(v)})
                nome = Path(str(linha.iloc[0]["arquivo"])).stem
        cv = curva_de_tabela(df, _tecnica_por_nome(f"{nome} {info.get('procedimento', '')}", df.columns), str(aba))
        if cv:
            saida.append((nome, info, cv))
    return saida
