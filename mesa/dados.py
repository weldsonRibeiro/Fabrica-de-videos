"""Velas (candles) de preço: CSV, gerador sintético para testar a estrutura e download de histórico público."""
from __future__ import annotations

import csv
import json
import math
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

INTERVALOS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


@dataclass(frozen=True)
class Vela:
    t: int      # início da vela, em segundos (UTC)
    o: float
    h: float
    l: float
    c: float
    v: float


def salvar_csv(velas: list[Vela], caminho: Path | str) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        for x in velas:
            w.writerow([x.t, x.o, x.h, x.l, x.c, x.v])


def ler_csv(caminho: Path | str) -> list[Vela]:
    with open(caminho, newline="", encoding="utf-8") as f:
        velas = [Vela(int(float(r["t"])), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"]))
                 for r in csv.DictReader(f)]
    velas.sort(key=lambda x: x.t)
    validar(velas)
    return velas


def validar(velas: list[Vela]) -> None:
    """Dado ruim é a maior fonte de backtest falso: recusa tempo repetido e preço impossível."""
    for a, b in zip(velas, velas[1:]):
        if b.t <= a.t:
            raise ValueError(f"tempo repetido ou fora de ordem em t={b.t}")
    for x in velas:
        if min(x.o, x.h, x.l, x.c) <= 0 or x.h < max(x.o, x.c) - 1e-9 or x.l > min(x.o, x.c) + 1e-9:
            raise ValueError(f"vela inconsistente em t={x.t}")


def sintetico(n: int = 8760, seed: int = 1, modo: str = "ruido", passo: int = 3600,
              preco0: float = 30000.0, vol: float = 0.005, inicio: int = 1_600_000_000) -> list[Vela]:
    """Preços inventados, só para testar a estrutura (NÃO são o mercado).

    modo "ruido":     passeio aleatório puro — não existe vantagem nenhuma; um sistema honesto não pode "achar" uma.
    modo "momentum":  retornos com autocorrelação positiva — existe uma vantagem pequena e conhecida.
    modo "regimes":   alterna períodos de tendência e de reversão, com volatilidade variável.
    """
    rnd = random.Random(seed)
    velas, preco, r_ant = [], preco0, 0.0
    regime, vol_atual = 1, vol
    for i in range(n):
        if modo == "regimes":
            if rnd.random() < 0.004:
                regime = -regime
            if rnd.random() < 0.01:
                vol_atual = vol * rnd.choice([0.6, 1.0, 1.0, 1.8])
        phi = {"ruido": 0.0, "momentum": 0.2, "regimes": 0.18 * regime}[modo]
        r = phi * r_ant + rnd.gauss(0, vol_atual if modo == "regimes" else vol)
        o = preco
        c = o * math.exp(r)
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 3)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 3)))
        v = 100 * (1 + 8 * abs(r) / vol) * rnd.uniform(0.7, 1.3)
        velas.append(Vela(inicio + i * passo, o, h, l, c, v))
        preco, r_ant = c, r
    return velas


Transporte = Callable[[str], bytes]


def _http(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def baixar_binance(simbolo: str = "BTCUSDT", intervalo: str = "1h", desde: int = 0, ate: int | None = None,
                   transporte: Transporte = _http, base: str = "https://api.binance.com") -> list[Vela]:
    """Histórico público (sem chave). Rode no SEU computador: algumas redes/países bloqueiam a Binance."""
    passo = INTERVALOS[intervalo]
    velas: list[Vela] = []
    inicio_ms = desde * 1000
    while True:
        url = f"{base}/api/v3/klines?symbol={simbolo}&interval={intervalo}&limit=1000&startTime={inicio_ms}"
        lote = json.loads(transporte(url))
        if not lote:
            break
        for k in lote:
            t = int(k[0]) // 1000
            if ate is not None and t > ate:
                return velas
            velas.append(Vela(t, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])))
        if len(lote) < 1000:
            break
        inicio_ms = (velas[-1].t + passo) * 1000
    return velas
