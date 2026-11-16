"""Risco: decide SE opera, QUANTO e QUANDO parar. É a parte que mais protege o capital."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ConfigRisco:
    fracao_kelly: float = 0.5          # usa só metade do tamanho "ótimo" de Kelly (o ótimo é agressivo demais)
    max_posicao: float = 0.5           # no máximo 50% do capital numa posição
    risco_por_operacao: float = 0.01   # no stop, perde no máximo 1% do capital
    margem_prob: float = 0.03          # só opera se a probabilidade passar de 50% ± 3 pontos
    stop_sigmas: float = 1.5           # stop a 1,5 desvios da variação esperada no horizonte
    perda_max_dia: float = 0.03        # perdeu 3% no dia: para até amanhã
    drawdown_max: float = 0.20         # caiu 20% do topo: DESLIGA tudo (kill switch)
    permitir_short: bool = False       # spot não vende a descoberto


@dataclass
class Decisao:
    direcao: int          # +1 comprado, -1 vendido, 0 fora
    fracao: float = 0.0   # fração do capital
    stop_pct: float = 0.0
    ev: float = 0.0       # valor esperado, já descontados os custos
    p_dir: float = 0.5
    motivo: str = ""


def avaliar_entrada(p: float, vol: float, horizonte: int, taxa_bps: float, slip_bps: float, cfg: ConfigRisco) -> Decisao:
    if p > 0.5 + cfg.margem_prob:
        d = 1
    elif cfg.permitir_short and p < 0.5 - cfg.margem_prob:
        d = -1
    else:
        return Decisao(0, motivo="sem vantagem (probabilidade perto de 50%)")
    p_dir = p if d > 0 else 1 - p
    mov = 0.8 * vol * math.sqrt(horizonte)             # |variação| típica no horizonte
    ev = (2 * p_dir - 1) * mov - 2 * (taxa_bps + slip_bps) / 1e4
    if ev <= 0:
        return Decisao(0, ev=ev, p_dir=p_dir, motivo="valor esperado não cobre os custos")
    stop = cfg.stop_sigmas * vol * math.sqrt(horizonte)
    f = min(cfg.max_posicao, cfg.fracao_kelly * (2 * p_dir - 1), cfg.risco_por_operacao / stop)
    return Decisao(d, f, stop, ev, p_dir)


class GuardaRisco:
    """Vigia o capital: limite de perda do dia e kill switch por drawdown."""

    def __init__(self, cfg: ConfigRisco, capital: float):
        self.cfg, self.pico, self.dia, self.abertura_dia = cfg, capital, None, capital
        self.desligado = False
        self.motivo = ""

    def atualizar(self, t: int, equity: float) -> None:
        dia = t // 86400
        if dia != self.dia:
            self.dia, self.abertura_dia = dia, equity
        self.pico = max(self.pico, equity)
        if not self.desligado and equity < self.pico * (1 - self.cfg.drawdown_max):
            self.desligado, self.motivo = True, f"KILL SWITCH: queda de {1 - equity / self.pico:.0%} desde o topo"

    def para_dict(self) -> dict:
        return {"pico": self.pico, "dia": self.dia, "abertura_dia": self.abertura_dia, "desligado": self.desligado, "motivo": self.motivo}

    def de_dict(self, d: dict) -> None:
        self.pico, self.dia, self.abertura_dia = d["pico"], d["dia"], d["abertura_dia"]
        self.desligado, self.motivo = d["desligado"], d["motivo"]

    def pode_operar(self, equity: float) -> tuple[bool, str]:
        if self.desligado:
            return False, self.motivo
        if equity < self.abertura_dia * (1 - self.cfg.perda_max_dia):
            return False, "limite de perda do dia atingido"
        return True, ""
