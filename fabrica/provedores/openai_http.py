"""Cliente HTTP mínimo (stdlib) para voz e imagem. 429 vira LimiteAtingido: a fábrica espera e retoma."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import timedelta
from typing import Callable

from .base import LimiteAtingido

URL_BASE = "https://api.openai.com/v1"

# transporte(url, headers, corpo_json) -> bytes ; injetável nos testes
Transporte = Callable[[str, dict[str, str], dict], bytes]


class ErroHTTP(Exception):
    pass


def transporte_urllib(url: str, headers: dict[str, str], corpo: dict) -> bytes:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:300]
        if e.code == 429:
            espera = e.headers.get("retry-after")
            raise LimiteAtingido(timedelta(seconds=int(espera)) if espera and espera.isdigit() else None,
                                 f"limite do provedor (429): {detalhe}") from e
        raise ErroHTTP(f"HTTP {e.code}: {detalhe}") from e
    except urllib.error.URLError as e:
        raise ErroHTTP(f"falha de rede: {e.reason}") from e


class ClienteOpenAI:
    def __init__(self, chave: str, transporte: Transporte = transporte_urllib):
        self._headers = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
        self._transporte = transporte

    def post(self, caminho: str, corpo: dict) -> bytes:
        return self._transporte(f"{URL_BASE}{caminho}", self._headers, corpo)
