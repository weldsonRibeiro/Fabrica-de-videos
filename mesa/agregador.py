"""O agregador: junta as leituras dos agentes numa probabilidade única — e mede se ela é honesta.

Uma probabilidade só vale se for CALIBRADA: nas vezes em que diz 70%, o preço tem de subir ~70% das vezes.
"""
from __future__ import annotations

import math
from typing import Sequence

from .leitores import Leitura, logit, sigmoide


def linha(leituras: Sequence[Leitura]) -> list[float]:
    """Uma linha de características: confiança x logit(prob) de cada leitor (0 = sem opinião)."""
    return [l.conf * logit(l.p) for l in leituras]


def _resolver(A: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        if abs(M[c][c]) < 1e-12:
            M[c][c] = 1e-12
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


class RegLog:
    """Regressão logística (Newton + ridge). Poucos parâmetros de propósito: dado financeiro é ruidoso e
    modelo grande só decora o passado."""

    def __init__(self, l2: float = 5.0, iteracoes: int = 12):
        self.l2, self.iteracoes = l2, iteracoes
        self.w: list[float] = []
        self.mu: list[float] = []
        self.sd: list[float] = []

    def _x(self, x: Sequence[float]) -> list[float]:
        return [1.0] + [max(-3.0, min(3.0, (v - m) / s)) for v, m, s in zip(x, self.mu, self.sd)]   # valores extremos são cortados em ±3 desvios

    def ajustar(self, X: list[list[float]], y: list[int]) -> None:
        k = len(X[0])
        self.mu = [sum(r[j] for r in X) / len(X) for j in range(k)]
        self.sd = [max(math.sqrt(sum((r[j] - self.mu[j]) ** 2 for r in X) / len(X)), 1e-9) for j in range(k)]
        Z = [self._x(r) for r in X]
        w = [0.0] * (k + 1)
        for _ in range(self.iteracoes):
            ps = [sigmoide(sum(a * b for a, b in zip(w, z))) for z in Z]
            g = [sum((p - yi) * z[j] for p, yi, z in zip(ps, y, Z)) + (self.l2 * w[j] if j else 0) for j in range(k + 1)]
            H = [[sum(p * (1 - p) * z[a] * z[b] for p, z in zip(ps, Z)) + (self.l2 if a == b and a else 0) for b in range(k + 1)]
                 for a in range(k + 1)]
            d = _resolver(H, g)
            w = [wi - di for wi, di in zip(w, d)]
            if max(abs(v) for v in d) < 1e-6:
                break
        self.w = w

    def prob(self, x: Sequence[float]) -> float:
        return sigmoide(sum(a * b for a, b in zip(self.w, self._x(x))))


class AgregadorMedia:
    """Linha de base: média simples das leituras. Se um modelo treinado não vencer isto, não vale a complexidade."""

    def __init__(self, colunas: list[int] | None = None):
        self.colunas = colunas

    def pronto(self) -> bool:
        return True

    def ajustar(self, X, y) -> None:
        pass

    def prob(self, x: Sequence[float]) -> float:
        usa = [x[i] for i in (self.colunas if self.colunas is not None else range(len(x)))]
        return sigmoide(sum(usa) / max(1, len(usa)))


class AgregadorLogistico:
    def __init__(self, colunas: list[int] | None = None, encolhimento: float = 0.6):
        self.colunas, self.m, self.encolhimento = colunas, None, encolhimento

    def pronto(self) -> bool:
        return self.m is not None

    def _sel(self, x):
        return [x[i] for i in self.colunas] if self.colunas is not None else list(x)

    def ajustar(self, X, y) -> None:
        m = RegLog()
        m.ajustar([self._sel(r) for r in X], y)
        self.m = m

    def prob(self, x: Sequence[float]) -> float:
        # encolhe em direção a 50%: dado financeiro é ruidoso e o modelo tende a se achar mais certo do que é
        return 0.5 + self.encolhimento * (self.m.prob(self._sel(x)) - 0.5)


def metricas(ps: Sequence[float], ys: Sequence[int], bins: int = 10) -> dict:
    """Brier e log-loss (menor é melhor; chutar 50% dá Brier 0,25 e log-loss 0,693) + tabela de calibração."""
    n = len(ps)
    if not n:
        return {"n": 0}
    brier = sum((p - y) ** 2 for p, y in zip(ps, ys)) / n
    ll = -sum(y * math.log(min(max(p, 1e-9), 1 - 1e-9)) + (1 - y) * math.log(min(max(1 - p, 1e-9), 1 - 1e-9)) for p, y in zip(ps, ys)) / n
    tabela = []
    for b in range(bins):
        sel = [(p, y) for p, y in zip(ps, ys) if int(min(p, 0.999999) * bins) == b]
        if sel:
            tabela.append({"faixa": f"{b / bins:.0%}-{(b + 1) / bins:.0%}", "n": len(sel),
                           "prob_media": sum(p for p, _ in sel) / len(sel), "freq_real": sum(y for _, y in sel) / len(sel)})
    return {"n": n, "brier": brier, "logloss": ll, "acuracia": sum((p > 0.5) == bool(y) for p, y in zip(ps, ys)) / n,
            "taxa_alta": sum(ys) / n, "tabela": tabela}
