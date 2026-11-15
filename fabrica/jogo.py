"""A camada de jogo: cada vídeo vira despesa da empresa, cada view vira moeda."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .armazem import Armazem

MOEDAS_POR_MIL_VIEWS = 10.0
_ARQUIVO = "carteira.json"


@dataclass
class Carteira:
    saldo: float = 0.0
    custo_lancado: dict[str, float] = field(default_factory=dict)  # video_id -> despesa já lançada
    views_lancadas: dict[str, int] = field(default_factory=dict)   # video_id -> views já convertidas
    historico: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def carregar(cls, armazem: Armazem) -> "Carteira":
        return cls(**armazem.carregar_json(_ARQUIVO, {}))

    def salvar(self, armazem: Armazem) -> None:
        armazem.salvar_json(_ARQUIVO, self.__dict__)

    def lancar_despesa(self, video_id: str, custo_total: float) -> float:
        """Idempotente: só lança a diferença ainda não cobrada. Devolve o valor lançado agora."""
        delta = round(custo_total - self.custo_lancado.get(video_id, 0.0), 2)
        if delta <= 0:
            return 0.0
        self.custo_lancado[video_id] = custo_total
        self.saldo = round(self.saldo - delta, 2)
        self.historico.append({"tipo": "despesa", "video": video_id, "valor": -delta})
        return delta

    def registrar_views(self, video_id: str, views_total: int) -> float:
        """Converte as views novas em moedas. Devolve as moedas ganhas agora."""
        novas = views_total - self.views_lancadas.get(video_id, 0)
        if novas <= 0:
            return 0.0
        moedas = round(novas / 1000 * MOEDAS_POR_MIL_VIEWS, 2)
        self.views_lancadas[video_id] = views_total
        self.saldo = round(self.saldo + moedas, 2)
        self.historico.append({"tipo": "views", "video": video_id, "valor": moedas})
        return moedas
