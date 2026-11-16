"""O maestro: monta a agenda, acorda a produção na hora certa, retoma o que pausou e publica o aprovado."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .armazem import Armazem
from .jogo import Carteira
from .modelos import Canal, Status, Video
from .pipeline import ESPERA_ERRO, Pipeline
from .provedores.base import LimiteAtingido, Publicador

HORA_DE_AGENDAR_AMANHA = 20  # à noite, o dia seguinte já está na agenda


def _hora(texto: str) -> time:
    h, m = texto.split(":")
    return time(int(h), int(m))


class Maestro:
    def __init__(self, armazem: Armazem, pipeline: Pipeline, canais: list[Canal], publicador: Publicador):
        self.armazem = armazem
        self.pipeline = pipeline
        self.canais = canais
        self.publicador = publicador

    # --- agenda -----------------------------------------------------------------------------
    def montar_agenda(self, dia: date) -> list[Video]:
        """Um vídeo por canal, cada um no seu horário. Idempotente: não duplica."""
        criados = []
        for canal in self.canais:
            video_id = f"{dia.isoformat()}-{canal.id}"
            if self.armazem.carregar_video(video_id) or not canal.temas:
                continue
            video = Video(
                id=video_id,
                canal_id=canal.id,
                tema=canal.temas[dia.toordinal() % len(canal.temas)],
                nicho=canal.nicho,
                perfil=canal.perfil.para_dict(),
                producao_em=datetime.combine(dia, _hora(canal.inicio_producao)),
            )
            self.armazem.salvar_video(video)
            criados.append(video)
        return criados

    # --- o relógio da fábrica ---------------------------------------------------------------
    def tick(self, agora: datetime) -> list[Video]:
        """Uma batida do maestro. Devolve os vídeos que mudaram de estado nesta batida."""
        self.montar_agenda(agora.date())
        if agora.hour >= HORA_DE_AGENDAR_AMANHA:
            self.montar_agenda(agora.date() + timedelta(days=1))

        mudaram = []
        for video in self.armazem.listar_videos():
            if self._deve_produzir(video, agora):
                mudaram.append(self.pipeline.rodar(video, agora))
            elif self._deve_publicar(video, agora):
                mudaram.append(self._publicar(video, agora))

        carteira = Carteira.carregar(self.armazem)
        for video in self.armazem.listar_videos():
            carteira.lancar_despesa(video.id, video.custo)
        carteira.salvar(self.armazem)
        return mudaram

    @staticmethod
    def _deve_publicar(video: Video, agora: datetime) -> bool:
        # APROVADO sem retomar_em = pronto para subir; com retomar_em = esperando cota/limite/erro
        return video.status is Status.APROVADO and (video.retomar_em is None or agora >= video.retomar_em)

    def _publicar(self, video: Video, agora: datetime) -> Video:
        """Sobe o aprovado. Cota estourada ou erro passageiro não perdem a aprovação: tenta de novo depois."""
        try:
            video.id_externo = self.publicador.agendar(video)
        except LimiteAtingido as limite:
            video.retomar_em = agora + (limite.esperar or timedelta(hours=1))
            video.erro = f"publicação adiada: {limite}"
        except Exception as erro:  # noqa: BLE001
            n = video.tentativas.get("publicacao", 0) + 1
            video.tentativas["publicacao"] = n
            if n >= self.pipeline.max_tentativas:
                video.status, video.erro = Status.FALHOU, f"publicacao: {erro}"
            else:
                video.retomar_em, video.erro = agora + ESPERA_ERRO, f"publicação, tentativa {n}: {erro}"
        else:
            video.status, video.retomar_em, video.erro = Status.AGENDADO_NO_CANAL, None, None
        self.armazem.salvar_video(video)
        return video

    @staticmethod
    def _deve_produzir(video: Video, agora: datetime) -> bool:
        if video.status is Status.AGENDADO:
            return agora >= video.producao_em
        if video.status is Status.PAUSADO:
            return video.retomar_em is not None and agora >= video.retomar_em
        return False


# --- aprovação (a única coisa que o dono faz) ----------------------------------------------------
def aprovar(armazem: Armazem, video_id: str, titulo: int, thumbnail: int, publicar_em: datetime) -> Video:
    """Escolhe título, thumbnail e horário. O maestro sobe e agenda na próxima batida."""
    video = armazem.carregar_video(video_id)
    if video is None:
        raise ValueError(f"vídeo não encontrado: {video_id}")
    if video.status is not Status.AGUARDANDO_APROVACAO:
        raise ValueError(f"vídeo {video_id} não está aguardando aprovação (status: {video.status.value})")
    titulos, thumbs = video.pacote["titulos"], video.pacote["thumbnails"]
    if not 0 <= titulo < len(titulos) or not 0 <= thumbnail < len(thumbs):
        raise ValueError("título ou thumbnail fora das opções disponíveis")
    video.escolha = {"titulo": titulos[titulo], "thumbnail": thumbs[thumbnail], "publicar_em": publicar_em.isoformat()}
    video.status = Status.APROVADO
    armazem.salvar_video(video)
    return video
