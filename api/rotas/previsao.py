"""Previsão avulsa (arquivos enviados, sem gravar a coleta), modelo em uso e conversões."""
from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from fiep import __version__, db
from fiep.ingest import ingerir
from fiep.predict import prever, resumo_por_amostra

from .. import arquivos as up
from ..deps import sessao, usuario_atual
from ..modelo import limpo, registros

r = APIRouter(prefix="/api", tags=["previsão"])


@r.get("/saude", tags=["sistema"])
def saude(request: Request):
    try:
        mod = request.app.state.modelo.pacote()["cartao"]["id"]
    except Exception:  # noqa: BLE001
        mod = None
    return {"status": "ok", "versao": __version__, "modelo": mod}


@r.get("/modelo")
def modelo(request: Request, _=Depends(usuario_atual)):
    c = request.app.state.modelo.pacote()["cartao"]
    return {k: limpo(v) if not isinstance(v, dict) else {kk: limpo(vv) for kk, vv in v.items()} for k, v in c.items()}


@r.post("/prever")
async def api_prever(request: Request, arquivos: list[UploadFile] = File(...), caminhos: list[str] = Form(default=[]),
                     salvar: bool = Form(default=False), s: Session = Depends(sessao), u=Depends(usuario_atual)):
    """Classifica os voltamogramas enviados. Uma pasta por amostra (via `caminhos`); sem pastas, o
    envio inteiro é uma amostra."""
    modelo = request.app.state.modelo
    pacote = modelo.pacote()
    tmp = Path(tempfile.mkdtemp(prefix="fiep_"))
    try:
        await up.salvar(arquivos, tmp / "envio", caminhos)
        try:
            ds = ingerir(tmp, cfg=pacote["cfg"])
        except FileNotFoundError as e:
            raise HTTPException(400, "Nenhum voltamograma encontrado nos arquivos (.nox ou Excel/CSV do NOVA).") from e
        res = prever(ds, pacote, niveis=modelo.niveis())
        am = resumo_por_amostra(res)
        if salvar and len(res):
            db.gravar_predicoes(s, res, pacote["cartao"], modelo.pasta, usuario_id=u.id)
        avisos = ds.relatorio.loc[ds.relatorio["tipo"] == "aviso", "detalhe"].astype(str).tolist()
        return {"modelo": pacote["cartao"]["id"], "algoritmo": pacote["cartao"]["modelo"],
                "limiar": pacote["limiar"], "amostras": registros(am), "resultados": registros(res),
                "resumo": res["resultado"].value_counts().to_dict() if len(res) else {}, "avisos": avisos}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@r.post("/excel")
async def api_excel(arquivos: list[UploadFile] = File(...), caminhos: list[str] = Form(default=[]),
                    _=Depends(usuario_atual)):
    """Converte .nox para Excel (formato do NOVA) e devolve um .zip."""
    from fiep.excel import converter_pasta
    tmp = Path(tempfile.mkdtemp(prefix="fiep_"))
    try:
        salvos = await up.salvar(arquivos, tmp / "envio", caminhos)
        if not any(p.suffix.lower() == ".nox" for p in salvos):
            raise HTTPException(400, "Envie arquivos .nox para converter.")
        gerados = converter_pasta(tmp / "envio", tmp / "excel")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for g in gerados:
                z.write(g, g.relative_to(tmp / "excel").as_posix())
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="voltamogramas_excel.zip"'})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
