"""Dados de demonstração: um dia inventado na fábrica, para ver o painel sem chaves nem gastos."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .armazem import Armazem
from .fuso import agora_local
from .jogo import Carteira
from .modelos import ETAPAS, Status, Video

CANAIS_DEMO = [
    {"id": "historias", "nome": "Histórias Perdidas", "nicho": "história", "inicio_producao": "05:30", "temas": ["A biblioteca de Alexandria"],
     "perfil": {"voz": "onyx", "tom": "misterioso e envolvente", "estilo_visual": "pintura a óleo cinematográfica, tons quentes", "evitar": ["política partidária atual"], "cenas": 12}},
    {"id": "financas", "nome": "Dinheiro Sem Medo", "nicho": "finanças", "inicio_producao": "07:00", "temas": ["Juros compostos na prática"]},
    {"id": "ciencia", "nome": "Ciência em 10", "nicho": "ciência", "inicio_producao": "09:00", "temas": ["Buracos negros"]},
    {"id": "games", "nome": "Fase Final", "nicho": "games", "inicio_producao": "12:00", "temas": ["A história do Mario"],
     "perfil": {"voz": "echo", "tom": "nostálgico e divertido", "publico": "gamers de 20 a 40 anos", "estilo_visual": "pixel art colorida, estilo 16 bits"}},
    {"id": "viagem", "nome": "Mundo Afora", "nicho": "viagem", "inicio_producao": "15:30", "temas": ["Roteiro em Lisboa"]},
]


def _arquivo(pasta: Path, nome: str, conteudo: bytes = b"demo") -> str:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_bytes(conteudo)
    return str(pasta / nome)


def criar(armazem: Armazem, saida: Path, agora: datetime | None = None) -> None:
    """Cria, ao redor de `agora`, vídeos em cada estado possível."""
    agora = (agora or agora_local()).replace(second=0, microsecond=0)
    dia = agora.date()
    horario = lambda c: datetime.combine(dia, datetime.strptime(c["inicio_producao"], "%H:%M").time())  # noqa: E731

    def video(i: int, status: Status, feitas: int, **kw) -> Video:
        c = CANAIS_DEMO[i]
        v = Video(f"{dia}-{c['id']}", c["id"], c["temas"][0], horario(c), nicho=c["nicho"], status=status, **kw)
        for etapa in ETAPAS[:feitas]:
            v.artefatos[etapa.value] = {}
        v.custo = round(feitas * 1.1, 2)
        return v

    historias = video(0, Status.AGENDADO_NO_CANAL, 6)
    historias.id_externo = "demo"
    financas = video(1, Status.AGUARDANDO_APROVACAO, 6)
    pasta = saida / financas.id
    financas.artefatos["roteiro"] = {"titulos": ["Juros compostos: o segredo", "Como ficar rico devagar", "A matemática do dinheiro"],
                                    "shorts": [{"titulo": "O que são juros compostos?"}]}
    financas.pacote = {
        "video": _arquivo(pasta, "video.mp4"), "shorts": [_arquivo(pasta, "short-1.mp4")],
        "thumbnails": [_arquivo(pasta, f"thumb-{n}.jpg") for n in (1, 2, 3)],
        "titulos": financas.artefatos["roteiro"]["titulos"], "descricao": "Demo",
    }
    ciencia = video(2, Status.EM_PRODUCAO, 3)            # gravando a narração → cenas
    games = video(3, Status.PAUSADO, 4, retomar_em=agora + timedelta(minutes=47))  # bateu no limite na montagem
    viagem = video(4, Status.AGENDADO, 0)
    viagem.producao_em = agora + timedelta(hours=3)
    viagem.custo = 0.0

    for v in (historias, financas, ciencia, games, viagem):
        armazem.salvar_video(v)

    carteira = Carteira()
    for v in (historias, financas, ciencia, games):
        carteira.lancar_despesa(v.id, v.custo)
    carteira.registrar_views(historias.id, 5400)
    carteira.salvar(armazem)
