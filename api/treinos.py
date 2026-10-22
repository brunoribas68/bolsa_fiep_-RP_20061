"""Treinos disparados pela plataforma: rodam em segundo plano, um por vez, com o andamento visível.

O estado de cada treino fica em `resultados/treinos/<id>.json` (sobrevive a reinícios do servidor;
um treino interrompido pelo reinício aparece como "interrompido").
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
    def __init__(self, pasta_resultados: str | Path, pasta_modelos: str | Path, sessoes, config_pipeline: str | None):
        self.pasta = Path(pasta_resultados) / "treinos"
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.resultados, self.modelos = Path(pasta_resultados), Path(pasta_modelos)
        self.sessoes, self.config_pipeline = sessoes, config_pipeline
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
                 "mensagem": "", "modelo": None, "experimento": None}
            self._gravar(d)
            self._rodando = id_
        threading.Thread(target=self._rodar, args=(d,), daemon=True, name=f"treino-{id_}").start()
        return d

    def _rodar(self, d: dict) -> None:
        from fiep.config import load_config
        from fiep.divisao import de_banco
        from fiep.experimentos import rodar
        p = d["params"]

        def progresso(etapa, frac):
            d.update(etapa=etapa, progresso=round(float(frac), 3))
            self._gravar(d)

        try:
            d.update(estado="rodando", etapa="lendo o banco")
            self._gravar(d)
            cfg = load_config(self.config_pipeline)
            onde, params = None, ()
            if p.get("empresas"):
                onde = f"empresa_id IN ({', '.join('?' for _ in p['empresas'])})"
                params = tuple(int(e) for e in p["empresas"])
            if p.get("proporcoes"):
                cfg["divisao"] = {**cfg.get("divisao", {}), **p["proporcoes"]}
            s = self.sessoes()
            try:
                div, aviso = de_banco(s, cfg, onde, params, com_exemplo=bool(p.get("com_exemplo")))
            finally:
                s.close()
            d["divisao"] = div.descricao() + (f" {aviso}" if aviso else "")
            r = rodar(div, cfg, saida=self.resultados, pasta_modelos=self.modelos,
                      algoritmos=p.get("algoritmos") or None, variantes=p.get("variantes") or None,
                      ativar=bool(p.get("ativar")), progresso=progresso)
            res = r["resumo"]
            d.update(estado="concluido", progresso=1.0, etapa="concluído", modelo=res.get("modelo_registrado"),
                     experimento=res.get("experimento"),
                     mensagem=f"Melhor: {res['melhor']['modelo']} [{res['melhor']['variante']}] — "
                              f"acurácia balanceada no teste {res['melhor'].get('teste_balanced_accuracy', float('nan')):.3f}")
        except Exception as e:  # noqa: BLE001
            log.warning("Treino %s falhou: %s", d["id"], traceback.format_exc())
            d.update(estado="erro", mensagem=str(e))
        finally:
            d["terminado_em"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
            self._gravar(d)
            with self._trava:
                self._rodando = None
