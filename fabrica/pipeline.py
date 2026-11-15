"""O agente da sala: pesquisa → roteiro → narração → cenas → montagem → thumbnail.

Cada etapa concluída é salva na hora (checkpoint). Se a IA travar ou bater no limite do dia,
o vídeo fica PAUSADO com um horário para retomar — e continua exatamente da etapa onde parou.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .armazem import Armazem
from .modelos import ETAPAS, Etapa, Status, Video
from .provedores.base import LimiteAtingido, Provedor

ESPERA_ERRO = timedelta(minutes=5)


class Pipeline:
    def __init__(
        self,
        provedor: Provedor,
        armazem: Armazem,
        max_tentativas: int = 3,
        espera_limite: timedelta = timedelta(hours=1),
    ):
        self.provedor = provedor
        self.armazem = armazem
        self.max_tentativas = max_tentativas
        self.espera_limite = espera_limite

    def rodar(self, video: Video, agora: datetime) -> Video:
        video.status = Status.EM_PRODUCAO
        video.retomar_em = None
        video.erro = None

        for etapa in ETAPAS:
            if etapa.value in video.artefatos:
                continue  # já feita numa rodada anterior
            try:
                resultado = self.provedor.executar(etapa, video)
            except LimiteAtingido as limite:
                self._pausar(video, agora + (limite.esperar or self.espera_limite))
                return video
            except Exception as erro:  # noqa: BLE001 — qualquer falha vira nova tentativa
                n = video.tentativas.get(etapa.value, 0) + 1
                video.tentativas[etapa.value] = n
                if n >= self.max_tentativas:
                    video.status = Status.FALHOU
                    video.erro = f"{etapa.value}: {erro}"
                    self.armazem.salvar_video(video)
                    return video
                self._pausar(video, agora + ESPERA_ERRO)
                return video

            video.artefatos[etapa.value] = resultado.artefato
            video.custo += resultado.custo
            self.armazem.salvar_video(video)  # checkpoint

        video.pacote = montar_pacote(video)
        video.status = Status.AGUARDANDO_APROVACAO
        self.armazem.salvar_video(video)
        return video

    def _pausar(self, video: Video, retomar_em: datetime) -> None:
        video.status = Status.PAUSADO
        video.retomar_em = retomar_em
        self.armazem.salvar_video(video)


def montar_pacote(video: Video) -> dict:
    """O que chega pro dono: vídeo, shorts, thumbnails e opções de título."""
    a = video.artefatos
    return {
        "video": a[Etapa.MONTAGEM.value]["video"],
        "shorts": a[Etapa.MONTAGEM.value]["shorts"],
        "thumbnails": a[Etapa.THUMBNAIL.value]["thumbnails"],
        "titulos": a[Etapa.ROTEIRO.value]["titulos"],
        "descricao": a[Etapa.ROTEIRO.value].get("descricao", ""),
    }
