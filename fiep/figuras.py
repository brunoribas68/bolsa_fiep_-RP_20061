"""Figuras (PNG) e tabelas/números (LaTeX) gerados por um experimento.

Tudo vai para a pasta do experimento e pode ser copiado para `artigo/gerado/` com
`fiep experimento ... --artigo`. As cores seguem uma paleta categórica validada para
daltonismo (slots 1-3) e uma escala sequencial de um só tom para mapas de calor.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
GRADE = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # slots 1-3: válidos em todos os pares
CLASSE = {0: SERIES[0], 1: SERIES[1]}
NOME_CLASSE = {0: "não contaminada", 1: "contaminada"}


def _plt():
    import sys

    import matplotlib
    if "ipykernel" not in sys.modules:      # fora do Jupyter: gera arquivos sem abrir janela
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight", "font.size": 9,
        "axes.edgecolor": TINTA_2, "axes.labelcolor": TINTA, "xtick.color": TINTA_2, "ytick.color": TINTA_2,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRADE,
        "grid.linewidth": 0.6, "axes.axisbelow": True, "lines.linewidth": 2, "legend.frameon": False,
        "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": TINTA,
    })
    return plt


def _br(x, casas=3) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "--"
    return f"{x:.{casas}f}".replace(".", ",")


# ----------------------------------------------------------------------------- figuras

def mapa_modelos(placar: pd.DataFrame, destino: Path):
    plt = _plt()
    from matplotlib.colors import LinearSegmentedColormap
    col = "val_balanced_accuracy" if "val_balanced_accuracy" in placar and placar["val_balanced_accuracy"].notna().any() \
        else "cv_balanced_accuracy"
    tab = placar.pivot_table(index="modelo", columns="variante", values=col)
    tab = tab.loc[tab.max(axis=1).sort_values(ascending=False).index]
    cmap = LinearSegmentedColormap.from_list("azul", ["#eef4fc", "#2a78d6", "#0d3c75"])
    fig, ax = plt.subplots(figsize=(1.3 + 1.15 * tab.shape[1], 0.9 + 0.32 * tab.shape[0]))
    ax.grid(False)
    vmin = np.nanmin(tab.values)
    im = ax.imshow(tab.values, cmap=cmap, vmin=max(0.5, vmin - 0.02), vmax=1.0, aspect="auto")
    ax.set_xticks(range(tab.shape[1]), tab.columns, rotation=30, ha="right")
    ax.set_yticks(range(tab.shape[0]), tab.index)
    melhor = np.unravel_index(np.nanargmax(tab.values), tab.shape)
    for i in range(tab.shape[0]):
        for j in range(tab.shape[1]):
            v = tab.values[i, j]
            if np.isfinite(v):
                escuro = (v - im.norm.vmin) / (im.norm.vmax - im.norm.vmin) > 0.55
                ax.text(j, i, _br(v), ha="center", va="center", fontsize=7.5,
                        color="white" if escuro else TINTA, fontweight="bold" if (i, j) == melhor else "normal")
    ax.set_title("Acurácia balanceada no conjunto de validação" if col.startswith("val_")
                 else "Acurácia balanceada na validação cruzada agrupada (treino)")
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.outline.set_visible(False)
    fig.savefig(destino)
    plt.close(fig)


def roc_teste(prob_teste: dict, escolhidos: list, destino: Path):
    from sklearn.metrics import roc_auc_score, roc_curve
    plt = _plt()
    fig, ax = plt.subplots(figsize=(3.6, 3.4))
    ax.plot([0, 1], [0, 1], color=GRADE, lw=1, ls="--")
    for cor, chave in zip(SERIES, escolhidos):
        if chave not in prob_teste:
            continue
        y, p = prob_teste[chave]
        if len(set(y)) < 2:
            continue
        fpr, tpr, _ = roc_curve(y, p)
        ax.plot(fpr, tpr, color=cor, label=f"{chave[1]} [{chave[0]}]  AUC {_br(roc_auc_score(y, p))}")
    ax.set_xlabel("1 − especificidade")
    ax.set_ylabel("sensibilidade")
    ax.set_title("Curva ROC no conjunto de teste")
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.01, 1.01)
    ax.legend(loc="lower right", fontsize=7)
    fig.savefig(destino)
    plt.close(fig)


def matriz_confusao(vp, fp, vn, fn, destino: Path, titulo: str):
    plt = _plt()
    from matplotlib.colors import LinearSegmentedColormap
    cm = np.array([[vn, fp], [fn, vp]])
    fig, ax = plt.subplots(figsize=(3.0, 2.8))
    ax.grid(False)
    ax.imshow(cm, cmap=LinearSegmentedColormap.from_list("azul", ["#eef4fc", "#2a78d6"]))
    for i in range(2):
        for j in range(2):
            ax.text(j, i, int(cm[i, j]), ha="center", va="center", fontsize=13,
                    color="white" if cm[i, j] > cm.max() * 0.6 else TINTA)
    ax.set_xticks([0, 1], ["prev. não\ncontaminada", "prev.\ncontaminada"])
    ax.set_yticks([0, 1], ["não\ncontaminada", "contaminada"])
    ax.set_title(titulo)
    fig.savefig(destino)
    plt.close(fig)


def curvas_diferenca(tab: pd.DataFrame, destino: Path):
    cols = [c for c in tab.columns if str(c).startswith("D_")]
    if not cols:
        return False
    plt = _plt()
    e = np.array([float(c[2:]) for c in cols])
    fig, ax = plt.subplots(figsize=(4.4, 3.0))
    for cls in (0, 1):
        sub = tab.loc[tab["contamination_status"] == cls, cols].astype(float)
        if sub.empty:
            continue
        m, s = sub.mean().to_numpy(), sub.std().to_numpy()
        ax.fill_between(e, m - s, m + s, color=CLASSE[cls], alpha=0.15, lw=0)
        ax.plot(e, m, color=CLASSE[cls], label=f"{NOME_CLASSE[cls]} (n = {len(sub)})")
    ax.axhline(0, color=TINTA_2, lw=0.8)
    ax.set_xlabel("Potencial (V)")
    ax.set_ylabel("Δi (último − penúltimo estágio) (µA)")
    ax.set_title("Curva de diferença entre estágios (média ± 1 dp)")
    ax.legend(fontsize=7)
    fig.savefig(destino)
    plt.close(fig)
    return True


def importancia(modelo, Xt: pd.DataFrame, yt: np.ndarray, destino: Path, n=15):
    from sklearn.inspection import permutation_importance
    if len(set(yt)) < 2 or len(yt) < 10:
        return None
    r = permutation_importance(modelo, Xt, yt, scoring="balanced_accuracy", n_repeats=10, random_state=0)
    imp = pd.Series(r.importances_mean, index=Xt.columns).sort_values(ascending=False).head(n)[::-1]
    plt = _plt()
    fig, ax = plt.subplots(figsize=(4.6, 0.6 + 0.24 * len(imp)))
    ax.barh(range(len(imp)), imp.values, color=SERIES[0], height=0.6)
    ax.set_yticks(range(len(imp)), [nome_curto(c) for c in imp.index], fontsize=7)
    ax.set_xlabel("queda na acurácia balanceada ao embaralhar")
    ax.set_title("Importância por permutação (teste)")
    ax.grid(axis="y", visible=False)
    fig.savefig(destino)
    plt.close(fig)
    return imp[::-1]


def regressao(y, p, destino: Path, titulo: str):
    plt = _plt()
    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    lo, hi = min(np.min(y), np.min(p)) - 0.2, max(np.max(y), np.max(p)) + 0.2
    ax.plot([lo, hi], [lo, hi], color=GRADE, lw=1, ls="--")
    ax.scatter(y, p, s=22, color=SERIES[1], edgecolor="white", linewidth=0.8)
    ax.set_xlabel("log10 UFC/mL (plaqueamento)")
    ax.set_ylabel("log10 UFC/mL (previsto)")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_title(titulo)
    fig.savefig(destino)
    plt.close(fig)


# ----------------------------------------------------------------------------- LaTeX

def _tex_escape(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%")
            .replace("&", r"\&").replace("#", r"\#").replace("$", r"\$"))


def nome_curto(s: str) -> str:
    """Nomes de características legíveis em tabelas, fórmulas e gráficos."""
    return (str(s).replace("capture_probe_16S_rRNA", "rRNA").replace("capture_probe", "sonda")
            .replace("carbon_clean", "carbono").replace("delta_", "Δ").replace("_vs_", " vs ")
            .replace("_largura_meia_altura", " FWHM").replace("_i_pico", " i_pico").replace("_e_pico", " E_pico")
            .replace("_area", " área").replace("_amplitude", " amplitude").replace("_i_min", " i_min"))


def _formula_tex(f: str | None) -> str:
    if not f:
        return "--"
    f = nome_curto(f).replace("  (termos padronizados)", "")
    f = _tex_escape(f).replace("σ", r"$\sigma$").replace("·", r"$\cdot$").replace("−", "$-$").replace("Δ", r"$\Delta$")
    return r"\texttt{\small " + f + "}"


def tabela_classificacao(placar: pd.DataFrame, destino: Path, n=10):
    linhas = []
    for _, r in placar.head(n).iterrows():
        linhas.append(" & ".join([
            str(int(r["posicao"])), _tex_escape(r["variante"]), _tex_escape(r["modelo"]),
            f"{_br(r['cv_balanced_accuracy'])} $\\pm$ {_br(r['cv_ba_desvio'])}",
            _br(r.get("val_balanced_accuracy")), _br(r.get("val_roc_auc")),
            _br(r.get("teste_balanced_accuracy")), _br(r.get("teste_sensibilidade")),
            _br(r.get("teste_especificidade")), _br(r.get("teste_roc_auc"))]) + r" \\")
    destino.write_text("\n".join([
        r"\begin{tabular}{rllccccccc}", r"\toprule",
        r" & & & CV (treino) & \multicolumn{2}{c}{Validação} & \multicolumn{4}{c}{Teste} \\",
        r"\cmidrule(lr){4-4}\cmidrule(lr){5-6}\cmidrule(lr){7-10}",
        r"\# & Variante & Modelo & AB & AB & AUC & AB & Sens. & Espec. & AUC \\", r"\midrule",
        *linhas, r"\bottomrule", r"\end{tabular}", ""]), encoding="utf-8")


def tabela_regressao(reg: pd.DataFrame, destino: Path):
    linhas = [" & ".join([_tex_escape(r["variante"]), _tex_escape(r["modelo"]), _br(r["cv_rmse"], 2),
                          _br(r.get("val_rmse"), 2), _br(r.get("val_r2"), 2),
                          _br(r.get("teste_rmse"), 2), _br(r.get("teste_r2"), 2)]) + r" \\"
              for _, r in reg.iterrows()]
    destino.write_text("\n".join([
        r"\begin{tabular}{llccccc}", r"\toprule",
        r" & & CV (treino) & \multicolumn{2}{c}{Validação} & \multicolumn{2}{c}{Teste} \\",
        r"\cmidrule(lr){3-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
        r"Variante & Modelo & RMSE & RMSE & $R^2$ & RMSE & $R^2$ \\", r"\midrule",
        *linhas, r"\bottomrule", r"\end{tabular}", ""]), encoding="utf-8")


def numeros(resumo: dict, melhor: pd.Series, reg: pd.DataFrame, destino: Path):
    """Macros LaTeX com os números do experimento: o texto do artigo usa \\ABteste etc."""
    def m(nome, valor):
        return f"\\newcommand{{\\{nome}}}{{{valor}}}"
    r0 = reg.iloc[0] if len(reg) else None
    linhas = [
        "% Gerado automaticamente por fiep experimento — não edite à mão",
        m("ExpId", resumo["experimento"]),
        m("TipoTeste", _tex_escape(resumo["teste"])),
        m("NAmostrasTreino", resumo["amostras_treino"]), m("NAmostrasTeste", resumo["amostras_teste"]),
        m("NAmostrasValidacao", resumo.get("amostras_validacao", 0)),
        m("NReplicasTreino", resumo["replicas_treino"]), m("NReplicasTeste", resumo["replicas_teste"]),
        m("NReplicasValidacao", resumo.get("replicas_validacao", 0)),
        m("PropTreino", round(resumo.get("proporcoes", {}).get("treino", 0) * 100)),
        m("PropValidacao", round(resumo.get("proporcoes", {}).get("validacao", 0) * 100)),
        m("PropTeste", round(resumo.get("proporcoes", {}).get("teste", 0) * 100)),
        m("CriterioEscolha", _tex_escape(resumo.get("criterio_escolha", "validação cruzada no treino"))),
        m("NCombinacoes", resumo["combinacoes_avaliadas"]),
        m("MelhorModelo", _tex_escape(melhor["modelo"])), m("MelhorVariante", _tex_escape(melhor["variante"])),
        m("ABcv", _br(melhor["cv_balanced_accuracy"])), m("ABcvDP", _br(melhor["cv_ba_desvio"])),
        m("AUCcv", _br(melhor["cv_roc_auc"])),
        m("ABval", _br(melhor.get("val_balanced_accuracy"))), m("AUCval", _br(melhor.get("val_roc_auc"))),
        m("ABteste", _br(melhor.get("teste_balanced_accuracy"))),
        m("SENSteste", _br(melhor.get("teste_sensibilidade"))),
        m("ESPECteste", _br(melhor.get("teste_especificidade"))),
        m("AUCteste", _br(melhor.get("teste_roc_auc"))),
        m("Limiar", _br(melhor["limiar"], 2)),
        m("RegModelo", _tex_escape(r0["modelo"]) if r0 is not None else "--"),
        m("RegRMSEcv", _br(r0["cv_rmse"], 2) if r0 is not None else "--"),
        m("RegRMSEval", _br(r0.get("val_rmse"), 2) if r0 is not None else "--"),
        m("RegRMSEteste", _br(r0.get("teste_rmse"), 2) if r0 is not None else "--"),
        m("RegRdoisTeste", _br(r0.get("teste_r2"), 2) if r0 is not None else "--"),
        m("FormulaSISSO", _formula_tex(resumo.get("formula_sisso"))),
    ]
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- tudo

def gerar_todas(pasta: Path, placar, prob_teste, melhor_chave, tabelas, reg, reg_pred, modelo_final, resumo):
    fig = pasta / "figuras"
    tex = pasta / "tabelas"
    fig.mkdir(exist_ok=True)
    tex.mkdir(exist_ok=True)
    melhor = placar.iloc[0]
    mapa_modelos(placar, fig / "comparacao_modelos.png")
    # ROC: melhor combinação + o melhor de outras duas famílias de modelo
    import re

    def familia(nome):                       # log_reg, log_reg_C0.1 e log_reg_l1 são a mesma família
        return re.split(r"_(?:C[\d.]+|l1)$", str(nome))[0]

    outros, vistas = [], {familia(melhor["modelo"])}
    for _, r in placar.iterrows():
        if familia(r["modelo"]) not in vistas:
            outros.append((r["variante"], r["modelo"]))
            vistas.add(familia(r["modelo"]))
        if len(outros) == 2:
            break
    roc_teste(prob_teste, [melhor_chave, *outros], fig / "roc_teste.png")
    if "teste_vp" in melhor and pd.notna(melhor.get("teste_vp")):
        matriz_confusao(melhor["teste_vp"], melhor["teste_fp"], melhor["teste_vn"], melhor["teste_fn"],
                        fig / "matriz_confusao_teste.png", f"{melhor['modelo']} — teste")
    v_curva = melhor_chave[0] if any(str(c).startswith("D_") for c in tabelas[melhor_chave[0]][0].columns) \
        else next((v for v in tabelas if any(str(c).startswith("D_") for c in tabelas[v][0].columns)), None)
    if v_curva:
        curvas_diferenca(tabelas[v_curva][0], fig / "curvas_diferenca.png")
    tab_tr, _, tab_te, _, feats, _, _ = tabelas[melhor_chave[0]]
    if len(tab_te):
        imp = importancia(modelo_final, tab_te.reindex(columns=feats).astype(float),
                          tab_te["contamination_status"].astype(int).to_numpy(), fig / "importancia.png")
        if imp is not None:
            imp.rename("importancia").to_csv(pasta / "importancia.csv")
    if len(reg):
        r0 = reg.iloc[0]
        chave = (r0["variante"], r0["modelo"])
        if chave in reg_pred:
            regressao(*reg_pred[chave], fig / "regressao_teste.png", f"Carga bacteriana — {r0['modelo']} (teste)")
        tabela_regressao(reg, tex / "tabela_regressao.tex")
    tabela_classificacao(placar, tex / "tabela_classificacao.tex")
    numeros(resumo, melhor, reg, tex / "numeros.tex")
