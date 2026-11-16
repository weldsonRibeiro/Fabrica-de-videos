"""Corretora SIMULADA: ordens de mentirinha com taxa e derrapagem, estado salvo em disco.

NÃO existe aqui nenhuma ligação com corretora real. Quando existir, será outra classe com a mesma interface, atrás de
travas de segurança (veja docs/MESA.md).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Posicao:
    direcao: int
    unidades: float
    entrada: float
    stop: float
    t_entrada: int
    t_saida: int          # fim do prazo (horizonte)
    fracao: float
    p: float
    eq_antes: float


class CorretoraSimulada:
    def __init__(self, capital: float = 10_000.0, taxa_bps: float = 10.0, slippage_bps: float = 5.0):
        self.capital_inicial, self.caixa = capital, capital
        self.taxa, self.slip = taxa_bps / 1e4, slippage_bps / 1e4
        self.posicao: Posicao | None = None
        self.trades: list[dict] = []

    def equity(self, preco: float) -> float:
        return self.caixa + (self.posicao.direcao * self.posicao.unidades * preco if self.posicao else 0.0)

    def abrir(self, t: int, preco: float, direcao: int, fracao: float, stop_pct: float, p: float, t_saida: int) -> bool:
        if self.posicao or direcao == 0 or fracao <= 0:
            return False
        eq = self.caixa
        valor = fracao * eq
        entrada = preco * (1 + self.slip * direcao)
        unid = valor / entrada
        self.caixa += -direcao * unid * entrada - valor * self.taxa
        self.posicao = Posicao(direcao, unid, entrada, entrada * (1 - direcao * stop_pct), t, t_saida, fracao, p, eq)
        return True

    def fechar(self, t: int, preco: float, motivo: str) -> dict | None:
        pos = self.posicao
        if not pos:
            return None
        efetivo = preco * (1 - self.slip * pos.direcao)
        self.caixa += pos.direcao * pos.unidades * efetivo - pos.unidades * efetivo * self.taxa
        trade = {"t_entrada": pos.t_entrada, "t_saida": t, "direcao": pos.direcao, "entrada": round(pos.entrada, 2),
                 "saida": round(efetivo, 2), "p": round(pos.p, 4), "fracao": round(pos.fracao, 4), "motivo": motivo,
                 "ret_capital": (self.caixa - pos.eq_antes) / pos.eq_antes}
        self.trades.append(trade)
        self.posicao = None
        return trade

    def marcar(self, t: int, preco: float) -> dict | None:
        """Chamada a cada checagem de preço: fecha por stop (no preço observado, que pode ser pior) ou por prazo."""
        pos = self.posicao
        if not pos:
            return None
        if (pos.direcao > 0 and preco <= pos.stop) or (pos.direcao < 0 and preco >= pos.stop):
            return self.fechar(t, preco, "stop")
        if t >= pos.t_saida:
            return self.fechar(t, preco, "prazo")
        return None

    def para_dict(self) -> dict:
        return {"capital_inicial": self.capital_inicial, "caixa": self.caixa, "trades": self.trades,
                "posicao": asdict(self.posicao) if self.posicao else None}

    def de_dict(self, d: dict) -> None:
        self.capital_inicial, self.caixa, self.trades = d["capital_inicial"], d["caixa"], d["trades"]
        self.posicao = Posicao(**d["posicao"]) if d["posicao"] else None


def salvar_json(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)
