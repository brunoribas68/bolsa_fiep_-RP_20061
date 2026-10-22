"""A documentação acompanha o código: todo comando aparece no README e docs/COMANDOS.md está em dia."""
import argparse
from pathlib import Path

from fiep.cli import comandos_markdown, construir_parser

RAIZ = Path(__file__).resolve().parents[1]


def _comandos():
    sub = next(a for a in construir_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return sub.choices


def test_readme_cita_todos_os_comandos_e_acoes():
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    faltam = [n for n in _comandos() if f"fiep {n}" not in readme]
    for n, p in _comandos().items():
        acao = next((a for a in p._actions if a.dest == "acao"), None)
        faltam += [f"fiep {n} {c}" for c in (acao.choices if acao else []) if f"fiep {n} {c}" not in readme]
    assert not faltam, f"README sem: {faltam}"


def test_comandos_md_em_dia():
    atual = (RAIZ / "docs" / "COMANDOS.md").read_text(encoding="utf-8")
    assert atual == comandos_markdown(), "rode `fiep docs` para atualizar docs/COMANDOS.md"


def test_links_locais_do_readme_existem():
    import re
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    quebrados = [l for l in re.findall(r"\]\(([^)#]+)\)", readme)
                 if not l.startswith("http") and not (RAIZ / l).exists()]
    assert not quebrados, quebrados
