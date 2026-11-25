"""Treinos disparados pela plataforma: rodam em segundo plano, um por vez, com o andamento visível.

O estado de cada treino fica em `modelos/_treinos/<id>.json` (sobrevive a reinícios do servidor; um
treino interrompido pelo reinício aparece como "interrompido").
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import traceback
from pathlib import Path

log = logging.getLogger(__name__)


class Treinos:
    def __init__(self, pasta_modelos: str | Path, sessoes):
        self.modelos = Path(pasta_modelos)
        self.pasta = self.modelos / "_treinos"
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.sessoes = sessoes
        self._trava = threading.Lock()
        self._rodando: str | None = None
        for f in self.pasta.glob("*.json"):                # reinício no meio de um treino
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("estado") in ("na fila", "rodando"):
                d.update(estado="interrompido", mensagem="O servidor foi reiniciado durante o treino.")
                f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def _gravar(self, d: dict) -> None:
        (self.pasta / f"{d['id']}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2, default=str),
                                                    encoding="utf-8")

    def obter(self, id_: str) -> dict | None:
        f = self.pasta / f"{id_}.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def listar(self, n: int = 20) -> list[dict]:
        itens = [json.loads(f.read_text(encoding="utf-8")) for f in self.pasta.glob("*.json")]
        return sorted(itens, key=lambda d: d["criado_em"], reverse=True)[:n]

    def iniciar(self, params: dict, usuario: str) -> dict:
        with self._trava:
            if self._rodando:
                raise RuntimeError("Já há um treino em andamento; aguarde terminar.")
            id_ = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            d = {"id": id_, "estado": "na fila", "progresso": 0.0, "etapa": "preparando", "params": params,
                 "usuario": usuario, "criado_em": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                 "mensagem": "", "modelo": None}
            self._gravar(d)
            self._rodando = id_
        threading.Thread(target=self._rodar, args=(d,), daemon=True, name=f"treino-{id_}").start()
        return d

    def _rodar(self, d: dict) -> None:
        from fiep import genossensor, modelagem
        p = d["params"]

        def progresso(etapa, frac):
            d.update(etapa=etapa, progresso=round(float(frac), 3))
            self._gravar(d)

        s = self.sessoes()
        try:
            d.update(estado="rodando", etapa="lendo o banco")
            self._gravar(d)
            df = genossensor.tabela(s, incluir_curvas=True)
            if p.get("empresas"):
                df = df[df["empresa_id"].isin(p["empresas"])]
            pacote = modelagem.treinar(df, algoritmos=p.get("algoritmos") or None,
                                       variantes=p.get("variantes") or None, progresso=progresso)
            modelagem.salvar(pacote, self.modelos, ativar=bool(p.get("ativar")), s=s)
            c = pacote["cartao"]
            d.update(estado="concluido", progresso=1.0, etapa="concluído", modelo=c["id"],
                     mensagem=f"Melhor: {c['algoritmo_nome']} · {c['representacao_nome']} — acurácia balanceada "
                              f"{c['ab_referencia']:.3f} ({c['referencia']})")
        except Exception as e:  # noqa: BLE001
            log.warning("Treino %s falhou: %s", d["id"], traceback.format_exc())
            d.update(estado="erro", mensagem=str(e))
        finally:
            s.close()
            d["terminado_em"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
            self._gravar(d)
            with self._trava:
                self._rodando = None
