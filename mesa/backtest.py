"""Backtest honesto: nada de olhar o futuro, custos incluídos e um teste para não se enganar com sorte.

Linha do tempo de cada decisão:  fecha a vela k  →  leitores leem só até k  →  agregador (treinado só com o que já
terminou antes de k) dá a probabilidade  →  risco decide  →  a ordem é executada na ABERTURA da vela k+1.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .agregador import AgregadorLogistico, AgregadorMedia, linha, metricas
from .dados import Vela
from .leitores import Leitor, vol_por_vela
from .risco import ConfigRisco, GuardaRisco, avaliar_entrada


@dataclass
class Config:
    horizonte: int = 24                 # quantas velas dura cada operação (e a pergunta "sobe ou desce?")
    agregador: str = "logistico"        # "logistico" | "media"
    usar: list[int] | None = None       # índices dos leitores a usar (None = todos)
    retreino: int = 240                 # re-treina o agregador a cada N velas (walk-forward)
    treino_min: int = 500
    treino_max: int = 4000
    taxa_bps: float = 10.0              # corretagem por lado (0,10%)
    slippage_bps: float = 5.0           # derrapagem por lado
    capital: float = 10_000.0
    risco: ConfigRisco = field(default_factory=ConfigRisco)


@dataclass
class Preparado:
    velas: list[Vela]
    leitores: list[Leitor]
    horizonte: int
    inicio: int
    X: dict[int, list[float]]
    veto: dict[int, bool]
    vol: dict[int, float]
    y: dict[int, int]


def preparar(velas: list[Vela], leitores: list[Leitor], horizonte: int = 24) -> Preparado:
    """Calcula as leituras de cada vela UMA vez. Cada leitor só recebe o passado até aquela vela."""
    jmax = max(l.janela for l in leitores)
    X, veto, vol, y = {}, {}, {}, {}
    n = len(velas)
    for i in range(jmax, n):
        ls = [l.ler(velas[max(0, i + 1 - l.janela): i + 1]) for l in leitores]
        X[i] = linha(ls)
        veto[i] = any(l.veto for l in ls)
        vol[i] = vol_por_vela(velas[i - 48: i + 1])
        if i + horizonte < n:
            y[i] = int(velas[i + horizonte].c > velas[i + 1].o)
    return Preparado(velas, leitores, horizonte, jmax, X, veto, vol, y)


@dataclass
class Resultado:
    nome: str
    equity: list[float]
    trades: list[dict]
    retorno: float
    buy_hold: float
    sharpe: float
    max_dd: float
    exposicao: float
    prob: dict
    ic95: tuple[float, float]
    p_valor: float
    desligado: str = ""

    @property
    def significativo(self) -> bool:
        return len(self.trades) >= 30 and self.ic95[0] > 0


def _bootstrap(rets: list[float], seed: int = 7, n: int = 2000) -> tuple[tuple[float, float], float]:
    if len(rets) < 2:
        return (float("nan"), float("nan")), 1.0
    rnd = random.Random(seed)
    medias = sorted(sum(rnd.choice(rets) for _ in rets) / len(rets) for _ in range(n))
    return (medias[int(0.025 * n)], medias[int(0.975 * n)]), sum(m <= 0 for m in medias) / n


def rodar(prep: Preparado, cfg: Config, nome: str = "") -> Resultado:
    velas, H, n = prep.velas, prep.horizonte, len(prep.velas)
    cols = cfg.usar
    agg = AgregadorMedia(cols) if cfg.agregador == "media" else AgregadorLogistico(cols)
    guarda = GuardaRisco(cfg.risco, cfg.capital)
    caixa, pos, trades, equity, expostas = cfg.capital, None, [], [], 0
    ps, ys = [], []
    ultimo_treino = -10**9
    slip, taxa = cfg.slippage_bps / 1e4, cfg.taxa_bps / 1e4

    for k in range(prep.inicio, n - 1):
        v = velas[k]
        # (0) entrada pendente: a ordem decidida na vela anterior é executada na abertura desta
        if pos and not pos["ativa"] and pos["idx"] == k:
            preco = v.o * (1 + slip * pos["dir"])
            valor = pos["fracao"] * caixa_antes(caixa, pos)
            pos.update(unid=valor / preco, entrada=preco, ativa=True, eq_antes=caixa)
            caixa += -pos["dir"] * pos["unid"] * preco - valor * taxa
            pos["stop"] = preco * (1 - pos["dir"] * pos["stop_pct"])
        # (1) saída: stop dentro da vela (se tocou, assume que veio primeiro) ou fim do prazo
        if pos and pos["ativa"]:
            saiu, preco_saida = False, None
            if pos["dir"] > 0 and v.l <= pos["stop"]:
                saiu, preco_saida = True, min(v.o, pos["stop"])
            elif pos["dir"] < 0 and v.h >= pos["stop"]:
                saiu, preco_saida = True, max(v.o, pos["stop"])
            elif k - pos["idx"] + 1 >= H:
                saiu, preco_saida = True, v.c
            if saiu:
                efetivo = preco_saida * (1 - slip * pos["dir"])
                caixa += pos["dir"] * pos["unid"] * efetivo - pos["unid"] * efetivo * taxa
                pnl = caixa - pos["eq_antes"]
                trades.append({"t_entrada": velas[pos["idx"]].t, "t_saida": v.t, "dir": pos["dir"], "p": pos["p"],
                               "fracao": pos["fracao"], "ret_capital": pnl / pos["eq_antes"], "parou_no_stop": preco_saida != v.c})
                pos = None
        eq = caixa + (pos["dir"] * pos["unid"] * v.c if pos and pos["ativa"] else 0)
        equity.append(eq)
        expostas += bool(pos and pos["ativa"])
        guarda.atualizar(v.t, eq)

        # (2) treino walk-forward: só amostras cujo resultado JÁ É CONHECIDO em k (j + H <= k)
        if cfg.agregador == "logistico" and k - ultimo_treino >= cfg.retreino:
            js = [j for j in range(max(prep.inicio, k - H - cfg.treino_max), k - H + 1) if j in prep.y]
            if len(js) >= cfg.treino_min:
                agg.ajustar([prep.X[j] for j in js], [prep.y[j] for j in js])
                ultimo_treino = k
        if not agg.pronto():
            continue
        p = agg.prob(prep.X[k])
        if k in prep.y:
            ps.append(p)
            ys.append(prep.y[k])

        # (3) decisão
        if pos is None:
            ok, _ = guarda.pode_operar(eq)
            if ok and not prep.veto[k]:
                d = avaliar_entrada(p, prep.vol[k], H, cfg.taxa_bps, cfg.slippage_bps, cfg.risco)
                if d.direcao:
                    pos = {"dir": d.direcao, "fracao": d.fracao, "stop_pct": d.stop_pct, "p": d.p_dir, "idx": k + 1, "ativa": False}

    # posição aberta no fim: marca a mercado (sem inventar saída)
    rets = [b / a - 1 for a, b in zip(equity, equity[1:])]
    passo = velas[1].t - velas[0].t
    anual = 365 * 86400 / passo
    sd = math.sqrt(sum((r - sum(rets) / len(rets)) ** 2 for r in rets) / max(1, len(rets) - 1)) if rets else 0
    sharpe = (sum(rets) / len(rets)) / sd * math.sqrt(anual) if sd > 0 else 0.0
    pico, dd = equity[0], 0.0
    for e in equity:
        pico = max(pico, e)
        dd = max(dd, 1 - e / pico)
    ic, pv = _bootstrap([t["ret_capital"] for t in trades])
    return Resultado(nome, equity, trades, equity[-1] / cfg.capital - 1, velas[n - 1].c / velas[prep.inicio].c - 1, sharpe, dd,
                     expostas / max(1, len(equity)), metricas(ps, ys), ic, pv, guarda.motivo)


def caixa_antes(caixa: float, pos: dict) -> float:
    return caixa  # tamanho da posição = fração do capital livre no momento da execução


def comparar(velas: list[Vela], leitores: list[Leitor], cfg: Config | None = None) -> list[Resultado]:
    """A estratégia completa contra as linhas de base: média simples e cada leitor sozinho."""
    cfg = cfg or Config()
    return comparar_prep(preparar(velas, leitores, cfg.horizonte), leitores, cfg)


def comparar_prep(prep: Preparado, leitores: list[Leitor], cfg: Config) -> list[Resultado]:
    from dataclasses import replace

    saidas = [rodar(prep, replace(cfg, agregador="logistico", usar=None), "agentes + logístico"),
              rodar(prep, replace(cfg, agregador="media", usar=None), "agentes + média simples")]
    for i, l in enumerate(leitores):
        if l.nome != "regime de volatilidade":
            saidas.append(rodar(prep, replace(cfg, agregador="media", usar=[i]), f"só {l.nome}"))
    return saidas
