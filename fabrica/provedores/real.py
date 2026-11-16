"""O provedor de verdade: Claude (pesquisa/roteiro), voz e imagem (OpenAI), ffmpeg (montagem)."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from ..config import Config
from ..modelos import Etapa, Video
from . import montagem
from .base import Resultado
from .claude import ClienteClaude
from .contabil import CustoPendente
from .openai_http import ClienteOpenAI

TAMANHO_IMAGEM = "1536x1024"


class ProvedorReal:
    def __init__(self, config: Config, claude: ClienteClaude | None = None, openai: ClienteOpenAI | None = None):
        montagem.exigir_ffmpeg()
        self.cfg = config
        self.claude = claude or ClienteClaude(config)
        self.openai = openai or ClienteOpenAI(config.openai_key)

    def executar(self, etapa: Etapa, video: Video) -> Resultado:
        pasta = self.cfg.saida / video.id
        pasta.mkdir(parents=True, exist_ok=True)
        pendente = CustoPendente(pasta)
        metodo = getattr(self, f"_{etapa.value}")
        artefato = metodo(video, pasta, pendente)
        return Resultado(artefato=artefato, custo=pendente.descarregar())

    # --- etapas ---------------------------------------------------------------------------------
    def _pesquisa(self, v: Video, pasta: Path, custo: CustoPendente) -> dict[str, Any]:
        r = self.claude.pesquisar(v.tema, v.nicho)
        custo.somar(r.custo)
        return {"dossie": r.texto, "fontes": r.fontes}

    def _roteiro(self, v: Video, pasta: Path, custo: CustoPendente) -> dict[str, Any]:
        roteiro, c = self.claude.roteirizar(v.tema, v.nicho, v.artefatos["pesquisa"]["dossie"])
        custo.somar(c)
        return roteiro

    def _narracao(self, v: Video, pasta: Path, custo: CustoPendente) -> dict[str, Any]:
        audios = []
        for i, cena in enumerate(v.artefatos["roteiro"]["cenas"], 1):
            arquivo = pasta / f"narracao-{i:02d}.mp3"
            if not arquivo.exists():  # já gerada antes do limite: não paga de novo
                dados = self.openai.post("/audio/speech", {
                    "model": self.cfg.modelo_voz, "voice": self.cfg.voz,
                    "input": cena["narracao"], "response_format": "mp3",
                    "instructions": "Narrador de documentário em português do Brasil: claro, caloroso e ritmado.",
                })
                arquivo.write_bytes(dados)
                custo.somar(montagem.duracao(arquivo) / 60 * self.cfg.custo_voz_por_min * self.cfg.cotacao)
            audios.append({"arquivo": str(arquivo), "duracao": montagem.duracao(arquivo)})
        return {"audios": audios}

    def _gerar_imagem(self, prompt: str, destino: Path, custo: CustoPendente) -> None:
        if destino.exists():
            return
        dados = self.openai.post("/images/generations", {
            "model": self.cfg.modelo_imagem, "prompt": prompt, "size": TAMANHO_IMAGEM,
            "quality": self.cfg.qualidade_imagem, "n": 1,
        })
        destino.write_bytes(base64.b64decode(json.loads(dados)["data"][0]["b64_json"]))
        custo.somar(self.cfg.custo_por_imagem * self.cfg.cotacao)

    def _cenas(self, v: Video, pasta: Path, custo: CustoPendente) -> dict[str, Any]:
        imagens = []
        for i, cena in enumerate(v.artefatos["roteiro"]["cenas"], 1):
            destino = pasta / f"cena-{i:02d}.png"
            self._gerar_imagem(cena["prompt_imagem"], destino, custo)
            imagens.append(str(destino))
        return {"cenas": imagens}

    def _montagem(self, v: Video, pasta: Path, custo: CustoPendente) -> dict[str, Any]:
        imagens = [Path(p) for p in v.artefatos["cenas"]["cenas"]]
        audios = [Path(a["arquivo"]) for a in v.artefatos["narracao"]["audios"]]
        clipes = []
        for i, (img, aud) in enumerate(zip(imagens, audios, strict=True), 1):
            clipe = pasta / f"clipe-{i:02d}.mp4"
            if not clipe.exists():
                montagem.clipe_cena(img, aud, clipe)
            clipes.append(clipe)

        video = pasta / "video.mp4"
        montagem.juntar(clipes, video)

        shorts = []
        for j, s in enumerate(v.artefatos["roteiro"]["shorts"], 1):
            horizontal = pasta / f"short-{j}-h.mp4"
            vertical = pasta / f"short-{j}.mp4"
            montagem.juntar(clipes[s["cena_inicio"]: s["cena_fim"] + 1], horizontal)
            montagem.para_vertical(horizontal, vertical)
            horizontal.unlink()
            shorts.append(str(vertical))
        return {"video": str(video), "shorts": shorts, "duracao": montagem.duracao(video)}

    def _thumbnail(self, v: Video, pasta: Path, custo: CustoPendente) -> dict[str, Any]:
        thumbs = []
        for i, prompt in enumerate(v.artefatos["roteiro"]["thumbnails"], 1):
            bruta, final = pasta / f"thumb-{i}.png", pasta / f"thumb-{i}.jpg"
            self._gerar_imagem(prompt, bruta, custo)
            montagem.thumbnail_16x9(bruta, final)
            thumbs.append(str(final))
        return {"thumbnails": thumbs}
