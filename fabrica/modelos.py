"""Modelos de dados: canal, vídeo, etapas e status."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Etapa(str, Enum):
    """As etapas do agente da sala, na ordem em que acontecem."""

    PESQUISA = "pesquisa"      # vai até a estante e pesquisa o tema
    ROTEIRO = "roteiro"        # senta e escreve o roteiro
    NARRACAO = "narracao"      # entra na cabine e grava a narração
    CENAS = "cenas"            # desenha as cenas no quadro
    MONTAGEM = "montagem"      # monta o vídeo (e os shorts) no computador
    THUMBNAIL = "thumbnail"    # faz a thumbnail


ETAPAS: list[Etapa] = list(Etapa)


class Status(str, Enum):
    AGENDADO = "agendado"                        # na agenda, esperando a hora
    EM_PRODUCAO = "em_producao"
    PAUSADO = "pausado"                          # travou / bateu no limite; retoma sozinho
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"  # pronto; falta o dono aprovar
    APROVADO = "aprovado"                        # dono escolheu título, thumb e horário
    AGENDADO_NO_CANAL = "agendado_no_canal"      # subiu e está agendado na plataforma
    FALHOU = "falhou"


@dataclass
class Canal:
    id: str
    nome: str
    nicho: str
    inicio_producao: str  # "HH:MM" — hora em que a fábrica começa o vídeo do dia
    temas: list[str] = field(default_factory=list)

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Canal":
        return cls(
            id=d["id"],
            nome=d["nome"],
            nicho=d.get("nicho", ""),
            inicio_producao=d["inicio_producao"],
            temas=list(d.get("temas", [])),
        )


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


@dataclass
class Video:
    id: str
    canal_id: str
    tema: str
    producao_em: datetime
    nicho: str = ""
    status: Status = Status.AGENDADO
    artefatos: dict[str, dict[str, Any]] = field(default_factory=dict)  # saída de cada etapa
    tentativas: dict[str, int] = field(default_factory=dict)
    retomar_em: datetime | None = None
    pacote: dict[str, Any] = field(default_factory=dict)   # o que chega pro dono aprovar
    escolha: dict[str, Any] = field(default_factory=dict)  # o que o dono aprovou
    custo: float = 0.0
    views: int = 0
    id_externo: str | None = None
    erro: str | None = None

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "canal_id": self.canal_id,
            "tema": self.tema,
            "nicho": self.nicho,
            "producao_em": self.producao_em.isoformat(),
            "status": self.status.value,
            "artefatos": self.artefatos,
            "tentativas": self.tentativas,
            "retomar_em": self.retomar_em.isoformat() if self.retomar_em else None,
            "pacote": self.pacote,
            "escolha": self.escolha,
            "custo": self.custo,
            "views": self.views,
            "id_externo": self.id_externo,
            "erro": self.erro,
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Video":
        return cls(
            id=d["id"],
            canal_id=d["canal_id"],
            tema=d["tema"],
            producao_em=datetime.fromisoformat(d["producao_em"]),
            nicho=d.get("nicho", ""),
            status=Status(d["status"]),
            artefatos=d.get("artefatos", {}),
            tentativas=d.get("tentativas", {}),
            retomar_em=_dt(d.get("retomar_em")),
            pacote=d.get("pacote", {}),
            escolha=d.get("escolha", {}),
            custo=d.get("custo", 0.0),
            views=d.get("views", 0),
            id_externo=d.get("id_externo"),
            erro=d.get("erro"),
        )
