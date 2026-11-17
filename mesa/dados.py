"""Velas (candles) de preço: CSV, gerador sintético para testar a estrutura e download de histórico público."""
from __future__ import annotations

import csv
import json
import math
import random
import time
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
    # Sem User-Agent próprio, o do Python ("Python-urllib") é recusado (HTTP 403) por Coinbase e outras APIs públicas.
    req = urllib.request.Request(url, headers={"User-Agent": "mesa-pesquisa/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
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


def baixar_coinbase(produto: str = "BTC-USD", intervalo: str = "1h", desde: int = 0, ate: int | None = None,
                    transporte: Transporte = _http, base: str = "https://api.exchange.coinbase.com",
                    dormir: Callable[[float], None] = time.sleep, progresso: Callable[[int], None] | None = None) -> list[Vela]:
    """Histórico público da Coinbase (sem chave; funciona de IPs dos EUA). 300 velas por pedido, com pausa entre eles."""
    from datetime import datetime, timezone

    passo = INTERVALOS[intervalo]
    if intervalo not in ("1m", "5m", "15m", "1h", "1d"):
        raise ValueError("a Coinbase aceita 1m, 5m, 15m, 1h e 1d")
    agora = int(time.time())
    ate = min(ate, agora) if ate else agora
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    por_t: dict[int, Vela] = {}
    ini = (max(desde, 0) // passo) * passo
    while ini < ate:
        fim = min(ini + 300 * passo, ate)
        lote = json.loads(transporte(f"{base}/products/{produto}/candles?granularity={passo}&start={iso(ini)}&end={iso(fim)}"))
        for t, baixo, alto, abre, fecha, vol in lote:            # formato da Coinbase: [t, low, high, open, close, volume]
            por_t[int(t)] = Vela(int(t), float(abre), float(alto), float(baixo), float(fecha), float(vol))
        ini = fim
        if progresso:
            progresso(len(por_t))
        dormir(0.12)                                             # a API pública limita a ~10 pedidos por segundo
    return sorted((v for v in por_t.values() if v.t + passo <= ate), key=lambda v: v.t)


def contar_lacunas(velas: list[Vela]) -> int:
    """Quantas velas faltam no meio da série (a Coinbase omite velas sem negócio)."""
    if len(velas) < 2:
        return 0
    passo = min(b.t - a.t for a, b in zip(velas, velas[1:]))
    return sum((b.t - a.t) // passo - 1 for a, b in zip(velas, velas[1:]) if b.t - a.t > passo)


def preencher_lacunas(velas: list[Vela]) -> list[Vela]:
    """Mantém o espaçamento uniforme (os leitores contam velas = horas): onde faltou, repete o último fechamento, volume 0."""
    if len(velas) < 2:
        return velas
    passo = min(b.t - a.t for a, b in zip(velas, velas[1:]))
    saida = [velas[0]]
    for v in velas[1:]:
        t = saida[-1].t + passo
        while t < v.t:
            c = saida[-1].c
            saida.append(Vela(t, c, c, c, c, 0.0))
            t += passo
        saida.append(v)
    return saida
