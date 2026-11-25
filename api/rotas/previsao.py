"""Previsão de .nox enviados (sem gravar na base), modelo em uso e conversão para Excel."""
from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from fiep import __version__, modelagem

from .. import arquivos as up
from ..deps import sessao, usuario_atual
from ..modelo import limpo

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
    return request.app.state.modelo.pacote()["cartao"]


@r.post("/prever")
async def api_prever(request: Request, arquivos: list[UploadFile] = File(...), caminhos: list[str] = Form(default=[]),
                     salvar: bool = Form(default=False), s: Session = Depends(sessao), u=Depends(usuario_atual)):
    """Classifica cada .nox enviado (branco = não contaminado, RNA = contaminado) com o modelo em uso."""
    pacote = request.app.state.modelo.pacote()
    tmp = Path(tempfile.mkdtemp(prefix="fiep_"))
    try:
        salvos = [p for p in await up.salvar(arquivos, tmp, caminhos) if p.suffix.lower() == ".nox"]
        if not salvos:
            raise HTTPException(400, "Envie voltamogramas em .nox.")
        res = modelagem.prever_arquivos(pacote, salvos)
        if salvar:
            modelagem.gravar_predicoes(s, res, pacote["cartao"], usuario_id=u.id)
        resumo: dict = {}
        for x in res:
            resumo[x["resultado"]] = resumo.get(x["resultado"], 0) + 1
        return {"modelo": pacote["cartao"], "resultados": [{k: limpo(v) for k, v in x.items()} for x in res],
                "resumo": resumo}
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
