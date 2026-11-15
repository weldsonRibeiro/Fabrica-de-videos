"""Persistência simples em JSON (um arquivo por vídeo) — o estado sobrevive a travas e reinícios."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .modelos import Video


def _escrever_atomico(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


class Armazem:
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz)

    def _caminho_video(self, video_id: str) -> Path:
        return self.raiz / "videos" / f"{video_id}.json"

    def salvar_video(self, video: Video) -> None:
        _escrever_atomico(self._caminho_video(video.id), video.para_dict())

    def carregar_video(self, video_id: str) -> Video | None:
        caminho = self._caminho_video(video_id)
        if not caminho.exists():
            return None
        return Video.de_dict(json.loads(caminho.read_text(encoding="utf-8")))

    def listar_videos(self) -> list[Video]:
        pasta = self.raiz / "videos"
        if not pasta.exists():
            return []
        videos = [Video.de_dict(json.loads(p.read_text(encoding="utf-8"))) for p in pasta.glob("*.json")]
        return sorted(videos, key=lambda v: (v.producao_em, v.id))

    def carregar_json(self, nome: str, padrao: Any) -> Any:
        caminho = self.raiz / nome
        return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao

    def salvar_json(self, nome: str, dados: Any) -> None:
        _escrever_atomico(self.raiz / nome, dados)
