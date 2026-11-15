"""Contratos dos provedores. Troque o falso pelos reais sem mexer no resto da fábrica."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

from ..modelos import Etapa, Video


class LimiteAtingido(Exception):
    """A IA bateu no limite (de uso, de tokens, do dia). A fábrica espera e retoma de onde parou."""

    def __init__(self, esperar: timedelta | None = None, motivo: str = "limite atingido"):
        super().__init__(motivo)
        self.esperar = esperar


@dataclass
class Resultado:
    artefato: dict[str, Any] = field(default_factory=dict)
    custo: float = 0.0  # em reais (ou na moeda que você usar para a despesa)


class Provedor(Protocol):
    def executar(self, etapa: Etapa, video: Video) -> Resultado:
        """Executa uma etapa e devolve o artefato. Pode levantar LimiteAtingido."""


class Publicador(Protocol):
    def agendar(self, video: Video) -> str:
        """Sobe o vídeo, shorts e thumbnail escolhida e agenda. Devolve o id na plataforma."""
