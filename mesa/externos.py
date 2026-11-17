"""Dados de fora do preço: índice de medo e ganância e funding de contratos perpétuos.

Cada série guarda o instante em que o dado JÁ ERA PÚBLICO. O leitor só enxerga o que foi publicado até o instante da decisão.
"""
from __future__ import annotations

import bisect
import json
from typing import Callable, Iterable

from .dados import Transporte, _http


class Serie:
    """Pares (t_publicado, valor) em ordem; `ate(t, n)` devolve os n últimos publicados até t (nunca do futuro)."""

    def __init__(self, pontos: Iterable[tuple[int, float]] = ()):
        self.t: list[int] = []
        self.v: list[float] = []
        self.adicionar(pontos)

    def adicionar(self, pontos: Iterable[tuple[int, float]]) -> None:
        mapa = dict(zip(self.t, self.v))
        mapa.update({int(t): float(v) for t, v in pontos})
        self.t = sorted(mapa)
        self.v = [mapa[t] for t in self.t]

    def ate(self, t: int, n: int = 1) -> list[tuple[int, float]]:
        i = bisect.bisect_right(self.t, t)
        return list(zip(self.t[max(0, i - n): i], self.v[max(0, i - n): i]))

    def pontos(self) -> list[tuple[int, float]]:
        return list(zip(self.t, self.v))

    def __len__(self) -> int:
        return len(self.t)


def baixar_medo(transporte: Transporte = _http, base: str = "https://api.alternative.me") -> Serie:
    """Crypto Fear & Greed Index (0 = medo extremo, 100 = ganância extrema), diário, sem chave.
    Por cautela, o valor do dia só conta como conhecido 24 h depois do carimbo dele."""
    dados = json.loads(transporte(f"{base}/fng/?limit=0&format=json"))["data"]
    return Serie((int(d["timestamp"]) + 86400, float(d["value"])) for d in dados)


def baixar_funding_binance(simbolo: str = "BTCUSDT", desde: int = 0, ate: int | None = None, transporte: Transporte = _http,
                           base: str = "https://fapi.binance.com") -> Serie:
    """Funding dos perpétuos da Binance (a cada 8 h). Fora do Brasil/EUA pode ser bloqueado: nesse caso levanta erro."""
    pontos, inicio = [], desde * 1000
    while True:
        lote = json.loads(transporte(f"{base}/fapi/v1/fundingRate?symbol={simbolo}&limit=1000&startTime={inicio}"))
        pontos += [(int(x["fundingTime"]) // 1000, float(x["fundingRate"])) for x in lote]
        if len(lote) < 1000 or (ate and pontos[-1][0] >= ate):
            break
        inicio = int(lote[-1]["fundingTime"]) + 1
    return Serie(pontos)


def baixar_funding_bybit(simbolo: str = "BTCUSDT", desde: int = 0, ate: int | None = None, transporte: Transporte = _http,
                         base: str = "https://api.bybit.com") -> Serie:
    pontos, fim = [], (ate or 2**31) * 1000
    while True:
        url = f"{base}/v5/market/funding/history?category=linear&symbol={simbolo}&limit=200&endTime={fim}"
        lote = json.loads(transporte(url))["result"]["list"]          # mais recentes primeiro
        if not lote:
            break
        pontos += [(int(x["fundingRateTimestamp"]) // 1000, float(x["fundingRate"])) for x in lote]
        menor = min(int(x["fundingRateTimestamp"]) for x in lote)
        if len(lote) < 200 or menor // 1000 <= desde:
            break
        fim = menor - 1
    return Serie(p for p in pontos if p[0] >= desde)


FUNDING = {"binance": baixar_funding_binance, "bybit": baixar_funding_bybit}
