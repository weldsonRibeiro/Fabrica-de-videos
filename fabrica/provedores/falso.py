"""Provedores de mentirinha: deixam rodar a fábrica inteira sem gastar nada. Bons para testes e demo."""
from __future__ import annotations

from datetime import timedelta

from ..modelos import Etapa, Video
from .base import LimiteAtingido, Resultado

CUSTO_POR_ETAPA = {
    Etapa.PESQUISA: 0.20,
    Etapa.ROTEIRO: 0.50,
    Etapa.NARRACAO: 1.50,
    Etapa.CENAS: 3.00,
    Etapa.MONTAGEM: 1.00,
    Etapa.THUMBNAIL: 0.30,
}


class ProvedorFalso:
    def __init__(self, limites: dict[Etapa, int] | None = None, espera: timedelta = timedelta(hours=1)):
        # limites[etapa] = quantas vezes a etapa "bate no limite" antes de funcionar
        self._limites = dict(limites or {})
        self._espera = espera

    def executar(self, etapa: Etapa, video: Video) -> Resultado:
        if self._limites.get(etapa, 0) > 0:
            self._limites[etapa] -= 1
            raise LimiteAtingido(self._espera, f"limite do dia na etapa {etapa.value}")

        tema = video.tema
        if etapa is Etapa.PESQUISA:
            artefato = {"fontes": [f"fonte-1 sobre {tema}", f"fonte-2 sobre {tema}"]}
        elif etapa is Etapa.ROTEIRO:
            artefato = {
                "roteiro": f"Roteiro completo sobre {tema}",
                "titulos": [f"{tema}: o que ninguém conta", f"Tudo sobre {tema}", f"{tema} em 10 minutos"],
            }
        elif etapa is Etapa.NARRACAO:
            artefato = {"audio": f"saida/{video.id}/narracao.wav"}
        elif etapa is Etapa.CENAS:
            artefato = {"cenas": [f"saida/{video.id}/cena-{i}.png" for i in range(1, 4)]}
        elif etapa is Etapa.MONTAGEM:
            artefato = {
                "video": f"saida/{video.id}/video.mp4",
                "shorts": [f"saida/{video.id}/short-{i}.mp4" for i in range(1, 4)],
            }
        else:
            artefato = {"thumbnails": [f"saida/{video.id}/thumb-{i}.png" for i in range(1, 4)]}
        return Resultado(artefato=artefato, custo=CUSTO_POR_ETAPA[etapa])


class PublicadorFalso:
    def agendar(self, video: Video) -> str:
        return f"falso-{video.id}"
