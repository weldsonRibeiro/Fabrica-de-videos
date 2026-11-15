"""Configuração por variáveis de ambiente. Nenhuma chave fica no código nem no repositório."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ErroDeConfiguracao(Exception):
    pass


@dataclass
class Config:
    # Texto (pesquisa e roteiro) — Claude. A chave é lida pelo SDK (ANTHROPIC_API_KEY ou `ant auth login`).
    modelo: str = "claude-opus-5-5"
    esforco: str = "medium"        # low | medium | high | xhigh | max
    fallback: bool = True          # fallback server-side do Claude se a resposta for recusada
    cenas: int = 12                # nº de cenas por vídeo (~25-30 s de narração cada)

    # Voz e imagem — OpenAI (HTTP direto, sem dependências)
    openai_key: str = ""
    modelo_voz: str = "gpt-4o-mini-tts"
    voz: str = "onyx"
    modelo_imagem: str = "gpt-image-1"
    qualidade_imagem: str = "medium"

    # Saída e contabilidade
    saida: Path = Path("saida")
    cotacao: float = 1.0           # os custos são estimados em USD; multiplique p/ outra moeda (ex.: 5.5)
    custo_voz_por_min: float = 0.015   # ESTIMATIVA — confira a tabela de preços do provedor
    custo_por_imagem: float = 0.05     # ESTIMATIVA — confira a tabela de preços do provedor

    @classmethod
    def do_ambiente(cls, env: Mapping[str, str] | None = None, exigir_chaves: bool = True) -> "Config":
        env = os.environ if env is None else env
        c = cls(
            modelo=env.get("FABRICA_MODELO", cls.modelo),
            esforco=env.get("FABRICA_ESFORCO", cls.esforco),
            fallback=env.get("FABRICA_SEM_FALLBACK", "") == "",
            cenas=int(env.get("FABRICA_CENAS", cls.cenas)),
            openai_key=env.get("OPENAI_API_KEY", ""),
            modelo_voz=env.get("FABRICA_MODELO_VOZ", cls.modelo_voz),
            voz=env.get("FABRICA_VOZ", cls.voz),
            modelo_imagem=env.get("FABRICA_MODELO_IMAGEM", cls.modelo_imagem),
            qualidade_imagem=env.get("FABRICA_QUALIDADE_IMAGEM", cls.qualidade_imagem),
            saida=Path(env.get("FABRICA_SAIDA", "saida")),
            cotacao=float(env.get("FABRICA_COTACAO", cls.cotacao)),
            custo_voz_por_min=float(env.get("FABRICA_CUSTO_VOZ_MIN", cls.custo_voz_por_min)),
            custo_por_imagem=float(env.get("FABRICA_CUSTO_IMAGEM", cls.custo_por_imagem)),
        )
        if exigir_chaves and not c.openai_key:
            raise ErroDeConfiguracao("defina OPENAI_API_KEY (voz e imagens). Veja .env.example")
        return c
