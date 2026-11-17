"""Os agentes leitores: cada um olha o mercado de um jeito e devolve uma PROBABILIDADE de alta no horizonte.

Regra de ouro: um leitor só enxerga o passado. Ele recebe apenas a janela de velas até o instante atual —
nunca a lista inteira — para ser impossível "ver o futuro" por acidente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from .dados import Vela


def sigmoide(x: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def media(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def desvio(xs: Sequence[float]) -> float:
    m = media(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1))


def retornos(h: Sequence[Vela]) -> list[float]:
    return [math.log(b.c / a.c) for a, b in zip(h, h[1:])]


def vol_por_vela(h: Sequence[Vela], n: int = 48) -> float:
    r = retornos(h[-(n + 1):])
    return max(desvio(r), 1e-6)


def ema(xs: Sequence[float], n: int) -> float:
    k, e = 2 / (n + 1), xs[0]
    for x in xs[1:]:
        e = x * k + e * (1 - k)
    return e


@dataclass
class Leitura:
    nome: str
    p: float            # probabilidade de o preço estar mais alto daqui a `horizonte` velas
    conf: float         # 0..1: o quanto o leitor confia no que viu (0 = não tem opinião)
    veto: bool = False  # o leitor de risco pode vetar qualquer operação
    nota: str = ""


class Leitor(Protocol):
    nome: str
    janela: int

    def ler(self, h: Sequence[Vela]) -> Leitura: ...


class Tendencia:
    nome, janela = "tendência", 100

    def ler(self, h):
        c = [x.c for x in h]
        z = (ema(c, 12) - ema(c, 48)) / (c[-1] * vol_por_vela(h) * 6)
        return Leitura(self.nome, sigmoide(1.2 * z), min(1.0, abs(z) / 2), nota=f"z={z:+.2f}")


class Momentum:
    nome, janela = "momentum", 60

    def ler(self, h):
        r24 = math.log(h[-1].c / h[-25].c)
        z = r24 / (vol_por_vela(h) * math.sqrt(24))
        return Leitura(self.nome, sigmoide(0.8 * z), min(1.0, abs(z) / 2), nota=f"z={z:+.2f}")


class Reversao:
    nome, janela = "reversão à média", 60

    def ler(self, h):
        c = [x.c for x in h[-48:]]
        z = (c[-1] - media(c)) / max(desvio(c), 1e-9)
        return Leitura(self.nome, sigmoide(-0.7 * z), min(1.0, abs(z) / 2.5), nota=f"z={z:+.2f}")


class Fluxo:
    """Pico de volume na direção da vela: quem está comprando/vendendo com pressa."""
    nome, janela = "fluxo e volume", 60

    def ler(self, h):
        v = [x.v for x in h[-49:-1]]
        pico = h[-1].v / max(media(v), 1e-9)
        lado = 1 if h[-1].c >= h[-1].o else -1
        if pico <= 1.2:
            return Leitura(self.nome, 0.5, 0.0, nota="volume normal")
        return Leitura(self.nome, 0.5 + lado * 0.12 * math.tanh(pico - 1), min(1.0, (pico - 1) / 2), nota=f"volume x{pico:.1f}")


class Regime:
    """Não opina sobre direção: avisa quando o mercado está explosivo (vol curta >> vol longa) e VETA."""
    nome, janela = "regime de volatilidade", 120

    def __init__(self, limite: float = 2.2):
        self.limite = limite

    def ler(self, h):
        razao = vol_por_vela(h, 12) / vol_por_vela(h, 96)
        return Leitura(self.nome, 0.5, 0.0, veto=razao > self.limite, nota=f"vol curta/longa = {razao:.2f}")


class Noticias:
    """Leitor de notícias: recebe uma fonte `fonte(t) -> [(t_publicacao, sentimento -1..1)]`.
    Só usa itens publicados ATÉ o instante t (sem olhar o futuro). Sem fonte, não tem opinião.
    Na prática, `fonte` seria um classificador de manchetes (ex.: modelo de linguagem) com data de publicação."""
    nome, janela = "notícias", 2

    def __init__(self, fonte: Callable[[int], list[tuple[int, float]]] | None = None, meia_vida_h: float = 6.0):
        self.fonte, self.meia_vida = fonte, meia_vida_h * 3600

    def ler(self, h):
        t = h[-1].t + 0  # vela fechada em t (+ duração é ignorada de propósito: só conta o que já era público)
        itens = [(tp, s) for tp, s in (self.fonte(t) if self.fonte else []) if tp <= t]
        if not itens:
            return Leitura(self.nome, 0.5, 0.0, nota="sem notícias")
        pesos = [(math.exp(-(t - tp) / self.meia_vida), s) for tp, s in itens]
        s = sum(w * x for w, x in pesos) / max(sum(w for w, _ in pesos), 1e-9)
        return Leitura(self.nome, 0.5 + 0.15 * s, min(1.0, sum(w for w, _ in pesos) / 3), nota=f"sentimento {s:+.2f}")


def _agora(h: Sequence[Vela]) -> int:
    """Instante da decisão = fechamento da última vela da janela."""
    return h[-1].t + (h[-1].t - h[-2].t)


class MedoGanancia:
    """Índice de medo e ganância (contrário nos extremos: medo extremo inclina para alta, ganância extrema para baixa)."""
    nome, janela = "medo e ganância", 2

    def __init__(self, serie):
        self.serie = serie

    def ler(self, h):
        pts = self.serie.ate(_agora(h), 1)
        if not pts:
            return Leitura(self.nome, 0.5, 0.0, nota="sem dado")
        v = pts[-1][1]
        z = (50 - v) / 50
        return Leitura(self.nome, 0.5 + 0.06 * z, min(1.0, abs(v - 50) / 40), nota=f"índice {v:.0f}")


class Funding:
    """Funding dos perpétuos: muito positivo = compradores alavancados lotando um lado (inclina para baixo); muito negativo, o inverso."""
    nome, janela = "funding", 2

    def __init__(self, serie):
        self.serie = serie

    def ler(self, h):
        pts = self.serie.ate(_agora(h), 31)
        if len(pts) < 12:
            return Leitura(self.nome, 0.5, 0.0, nota="sem histórico")
        atual, resto = pts[-1][1], [v for _, v in pts[:-1]]
        z = (atual - media(resto)) / max(desvio(resto), 1e-9)
        return Leitura(self.nome, sigmoide(-0.5 * z), min(1.0, abs(z) / 3), nota=f"funding {atual * 100:+.4f}% (z={z:+.1f})")


def leitores_padrao(extras: Sequence[Leitor] = ()) -> list[Leitor]:
    return [Tendencia(), Momentum(), Reversao(), Fluxo(), Regime(), *extras]
