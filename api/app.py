"""API e página web da pipeline FIEP.

Rodar:
    fiep servir                          # http://127.0.0.1:8000
    uvicorn api.app:app --reload         # alternativa, da raiz do repositório

Variáveis de ambiente:
    FIEP_MODELOS  pasta de modelos (padrão: modelos) — usa o modelo em modelos/ATUAL
    FIEP_DB       se definida, as previsões são gravadas neste banco SQLite

Rotas:
    GET  /                  página de upload
    GET  /api/saude         status e modelo carregado
    GET  /api/modelo        cartão do modelo (métricas, limiar, commit, variante)
    POST /api/prever        arquivos .nox + planilha (ou tabelas) -> previsões
    POST /api/planilha      arquivos .nox -> planilha de metadados pré-preenchida (CSV)
    GET  /docs              documentação interativa (Swagger)
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from fiep import __version__
from fiep.ingest import ingerir
from fiep.model import carregar
from fiep.predict import prever

ESTATICO = Path(__file__).parent / "static"
EXTENSOES = {".nox", ".csv", ".xlsx", ".xls", ".txt"}
MAX_ARQUIVOS = 300
MAX_BYTES = 50 * 1024 * 1024

app = FastAPI(title="FIEP — detecção de contaminação por voltametria", version=__version__,
              description="Recebe voltamogramas (.nox do NOVA ou tabelas) e devolve a classificação "
                          "contaminada / não contaminada e a carga estimada, com o controle de qualidade.")

_estado: dict = {"pacote": None, "erro": None, "pasta": None}


def _pasta_modelos() -> str:
    return os.environ.get("FIEP_MODELOS", "modelos")


def pacote() -> dict:
    """Carrega (uma vez) o modelo atual; recarrega se ATUAL mudar."""
    pasta = _pasta_modelos()
    atual = Path(pasta) / "ATUAL"
    marca = atual.read_text().strip() if atual.exists() else None
    if _estado["pacote"] is None or _estado["pasta"] != (pasta, marca):
        try:
            _estado["pacote"] = carregar(pasta)
            _estado["erro"] = None
        except Exception as e:  # noqa: BLE001
            _estado["pacote"], _estado["erro"] = None, f"Nenhum modelo em '{pasta}': rode `fiep experimento` ou `fiep treinar`. ({e})"
        _estado["pasta"] = (pasta, marca)
    if _estado["pacote"] is None:
        raise HTTPException(503, _estado["erro"])
    return _estado["pacote"]


def _limpo(v):
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if v is pd.NA or (not isinstance(v, (str, list, dict)) and pd.isna(v)):
        return None
    return v


async def _salvar_uploads(arquivos: list[UploadFile], destino: Path) -> list[str]:
    destino.mkdir(parents=True, exist_ok=True)
    if not arquivos:
        raise HTTPException(400, "Envie pelo menos um arquivo.")
    if len(arquivos) > MAX_ARQUIVOS:
        raise HTTPException(400, f"No máximo {MAX_ARQUIVOS} arquivos por envio.")
    nomes = []
    for up in arquivos:
        nome = Path(up.filename or "").name
        if Path(nome).suffix.lower() not in EXTENSOES:
            raise HTTPException(400, f"Tipo de arquivo não aceito: {nome}. Envie .nox, .csv ou .xlsx.")
        conteudo = await up.read()
        if len(conteudo) > MAX_BYTES:
            raise HTTPException(400, f"{nome} passa de 50 MB.")
        (destino / nome).write_bytes(conteudo)
        nomes.append(nome)
    return nomes


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def pagina():
    return FileResponse(ESTATICO / "index.html")


@app.get("/api/saude")
def saude():
    try:
        p = pacote()
        return {"status": "ok", "versao": __version__, "modelo": p["cartao"]["id"]}
    except HTTPException as e:
        return {"status": "sem_modelo", "versao": __version__, "detalhe": e.detail}


@app.get("/api/modelo")
def modelo():
    c = pacote()["cartao"]
    return {k: _limpo(v) if not isinstance(v, dict) else {kk: _limpo(vv) for kk, vv in v.items()}
            for k, v in c.items()}


@app.post("/api/prever")
async def api_prever(arquivos: list[UploadFile] = File(..., description=".nox + planilha de metadados, ou tabelas")):
    p = pacote()
    tmp = Path(tempfile.mkdtemp(prefix="fiep_"))
    try:
        # sem planilha, os arquivos de um envio formam uma amostra (separada por dia de medição)
        await _salvar_uploads(arquivos, tmp / "envio")
        try:
            ds = ingerir(tmp)
        except FileNotFoundError as e:
            raise HTTPException(400, str(e)) from e
        res = prever(ds, p)
        avisos = ds.relatorio.loc[ds.relatorio["tipo"] == "aviso", "detalhe"].astype(str).tolist()
        if os.environ.get("FIEP_DB") and len(res):
            from fiep import db
            con = db.conectar(os.environ["FIEP_DB"])
            db.importar(con, ds, origem="api")
            db.gravar_predicoes(con, res, p["cartao"], _pasta_modelos())
            con.close()
        linhas = [{k: _limpo(v) for k, v in r.items()} for r in res.to_dict(orient="records")]
        resumo = res["resultado"].value_counts().to_dict() if len(res) else {}
        return {"modelo": p["cartao"]["id"], "algoritmo": p["cartao"]["modelo"], "resumo": resumo,
                "resultados": linhas, "avisos": avisos}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/api/planilha")
async def api_planilha(arquivos: list[UploadFile] = File(..., description="arquivos .nox")):
    from fiep.planilha import gerar_planilha
    tmp = Path(tempfile.mkdtemp(prefix="fiep_"))
    try:
        nomes = await _salvar_uploads(arquivos, tmp / "envio")
        if not any(n.lower().endswith(".nox") for n in nomes):
            raise HTTPException(400, "Envie arquivos .nox para gerar a planilha.")
        destino, _ = gerar_planilha(tmp / "envio")
        return Response(destino.read_bytes(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="metadados_nox.csv"'})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
