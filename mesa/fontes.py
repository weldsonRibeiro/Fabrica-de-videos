"""Fontes de dados ao vivo (APIs públicas, SEM chave): últimas velas fechadas e o último preço.

Escolha a bolsa conforme a região de onde o programa roda: a Binance global bloqueia IPs dos EUA; a Coinbase aceita.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Protocol

from .dados import INTERVALOS, Vela

Transporte = Callable[[str], bytes]


def _http(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "mesa-pesquisa/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


class Fonte(Protocol):
    passo: int

    def velas(self, n: int, agora: float | None = None) -> list[Vela]: ...
    def preco(self) -> float: ...


def so_fechadas(velas: list[Vela], passo: int, agora: float) -> list[Vela]:
    """Uma vela só vale depois de fechar; a última da API costuma estar em formação."""
    return sorted((v for v in velas if v.t + passo <= agora), key=lambda v: v.t)


class FonteCoinbase:
    """Coinbase Exchange (BTC-USD). Até 300 velas por pedido."""

    def __init__(self, produto: str = "BTC-USD", intervalo: str = "1h", transporte: Transporte = _http,
                 base: str = "https://api.exchange.coinbase.com"):
        if intervalo not in ("1m", "5m", "15m", "1h", "1d"):
            raise ValueError("a Coinbase aceita 1m, 5m, 15m, 1h e 1d")
        self.produto, self.passo, self._http, self.base = produto, INTERVALOS[intervalo], transporte, base

    def velas(self, n: int, agora: float | None = None) -> list[Vela]:
        agora = agora if agora is not None else time.time()
        fim, acumulado = int(agora), {}
        while len(acumulado) < n:
            ini = fim - 300 * self.passo
            iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
            lote = json.loads(self._http(f"{self.base}/products/{self.produto}/candles?granularity={self.passo}&start={iso(ini)}&end={iso(fim)}"))
            if not lote:
                break
            for t, baixo, alto, abre, fecha, vol in lote:           # formato da Coinbase: [t, low, high, open, close, volume]
                acumulado[int(t)] = Vela(int(t), float(abre), float(alto), float(baixo), float(fecha), float(vol))
            fim = ini
        return so_fechadas(list(acumulado.values()), self.passo, agora)[-n:]

    def preco(self) -> float:
        return float(json.loads(self._http(f"{self.base}/products/{self.produto}/ticker"))["price"])

    def livro(self) -> tuple[float, float, float, float]:
        """(melhor compra, melhor venda, qtd compra, qtd venda). A Coinbase não informa as quantidades no ticker: 0."""
        d = json.loads(self._http(f"{self.base}/products/{self.produto}/ticker"))
        return float(d["bid"]), float(d["ask"]), 0.0, 0.0


class FonteBinance:
    def __init__(self, simbolo: str = "BTCUSDT", intervalo: str = "1h", transporte: Transporte = _http, base: str = "https://api.binance.com"):
        self.simbolo, self.intervalo, self.passo, self._http, self.base = simbolo, intervalo, INTERVALOS[intervalo], transporte, base

    def velas(self, n: int, agora: float | None = None) -> list[Vela]:
        agora = agora if agora is not None else time.time()
        lote = json.loads(self._http(f"{self.base}/api/v3/klines?symbol={self.simbolo}&interval={self.intervalo}&limit={min(n + 1, 1000)}"))
        velas = [Vela(int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in lote]
        return so_fechadas(velas, self.passo, agora)[-n:]

    def preco(self) -> float:
        return float(json.loads(self._http(f"{self.base}/api/v3/ticker/price?symbol={self.simbolo}"))["price"])

    def livro(self) -> tuple[float, float, float, float]:
        d = json.loads(self._http(f"{self.base}/api/v3/ticker/bookTicker?symbol={self.simbolo}"))
        return float(d["bidPrice"]), float(d["askPrice"]), float(d["bidQty"]), float(d["askQty"])


FONTES = {"coinbase": FonteCoinbase, "binance": FonteBinance}
