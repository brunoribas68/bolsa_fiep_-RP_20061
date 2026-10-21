"""Sessão por cookie (JWT assinado, httpOnly, SameSite=Strict), proteção CSRF e limite de tentativas.

* A senha nunca sai do servidor: bcrypt (fiep/usuarios.py).
* O cookie não é acessível por JavaScript (httpOnly) e não vai em requisições de outros sites
  (SameSite=Strict). Toda requisição que altera dados precisa do cabeçalho `X-Requested-With: fiep`,
  que um formulário de outro site não consegue enviar — segunda barreira contra CSRF.
* O token leva a `versao_sessao` do usuário: trocar a senha ou desativar a conta derruba as sessões.
* Login: 5 falhas em 15 minutos para o mesmo e-mail ou IP bloqueiam novas tentativas por 15 minutos.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from collections import defaultdict, deque

import jwt

COOKIE = "fiep_sessao"
CABECALHO_CSRF = ("x-requested-with", "fiep")
ALGORITMO = "HS256"
MAX_FALHAS = 5
JANELA_S = 15 * 60


def criar_token(usuario_id: int, versao: int, segredo: str, horas: float) -> str:
    agora = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(usuario_id), "v": versao, "iat": agora,
                       "exp": agora + dt.timedelta(hours=horas)}, segredo, algorithm=ALGORITMO)


def ler_token(token: str, segredo: str) -> dict | None:
    try:
        return jwt.decode(token, segredo, algorithms=[ALGORITMO], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None


class LimiteTentativas:
    def __init__(self, max_falhas: int = MAX_FALHAS, janela_s: int = JANELA_S):
        self.max, self.janela = max_falhas, janela_s
        self._falhas: dict[str, deque] = defaultdict(deque)
        self._trava = threading.Lock()

    def _limpar(self, chave: str, agora: float) -> deque:
        q = self._falhas[chave]
        while q and agora - q[0] > self.janela:
            q.popleft()
        return q

    def bloqueado(self, *chaves: str) -> bool:
        agora = time.monotonic()
        with self._trava:
            return any(len(self._limpar(c, agora)) >= self.max for c in chaves)

    def falhou(self, *chaves: str) -> None:
        agora = time.monotonic()
        with self._trava:
            for c in chaves:
                self._limpar(c, agora).append(agora)

    def sucesso(self, *chaves: str) -> None:
        with self._trava:
            for c in chaves:
                self._falhas.pop(c, None)
