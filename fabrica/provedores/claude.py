"""Pesquisa e roteiro com Claude (SDK oficial `anthropic`)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from ..config import Config
from ..fuso import agora_local
from ..modelos import Perfil
from .base import LimiteAtingido

# US$ por 1M de tokens (entrada, saída). Só para estimar o custo que vira despesa no jogo.
PRECOS = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}
CUSTO_BUSCA_WEB = 0.01  # estimativa por busca
MAX_CONTINUACOES = 5

SYSTEM = (
    "Você é a equipe de conteúdo de um canal de YouTube em português do Brasil. "
    "Seja factual: não invente datas, números, citações ou fontes. "
    "Quando não tiver certeza de algo, diga que é incerto ou deixe de fora."
)

ESQUEMA_ROTEIRO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titulos": {"type": "array", "items": {"type": "string"}},
        "descricao": {"type": "string"},
        "cenas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"narracao": {"type": "string"}, "prompt_imagem": {"type": "string"}},
                "required": ["narracao", "prompt_imagem"],
                "additionalProperties": False,
            },
        },
        "thumbnails": {"type": "array", "items": {"type": "string"}},
        "shorts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "cena_inicio": {"type": "integer"},
                    "cena_fim": {"type": "integer"},
                },
                "required": ["titulo", "cena_inicio", "cena_fim"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["titulos", "descricao", "cenas", "thumbnails", "shorts"],
    "additionalProperties": False,
}


def descrever_canal(nicho: str, perfil: Perfil) -> str:
    """O bloco de texto que apresenta o canal ao modelo (nicho + identidade + a data de hoje)."""
    linhas = [f"Data de hoje: {agora_local():%d/%m/%Y}. Antes de afirmar qualquer coisa sobre fatos recentes, "
              "confirme o estado atual do assunto nas fontes (algo pode já ter acontecido, mudado ou sido adiado).",
              f"Canal sobre: {nicho or 'assuntos gerais'}."]
    if perfil.publico:
        linhas.append(f"Público: {perfil.publico}.")
    if perfil.tom:
        linhas.append(f"Tom do canal: {perfil.tom}.")
    if perfil.evitar:
        linhas.append("Nunca use nem aborde: " + "; ".join(perfil.evitar) + ".")
    return "\n".join(linhas)


class ErroDeIA(Exception):
    """Recusa ou resposta truncada — não adianta esperar, vira nova tentativa."""


@dataclass
class RespostaClaude:
    texto: str
    custo: float
    fontes: list[str]


def validar_roteiro(r: dict[str, Any], max_shorts: int | None = None) -> dict[str, Any]:
    """Confere o que o modelo devolveu; descarta shorts com índices inválidos."""
    cenas = r.get("cenas") or []
    if not cenas:
        raise ErroDeIA("roteiro sem cenas")
    if len(r.get("titulos") or []) < 1 or len(r.get("thumbnails") or []) < 1:
        raise ErroDeIA("roteiro sem títulos ou sem ideias de thumbnail")
    n = len(cenas)
    r["shorts"] = [
        s for s in r.get("shorts", []) if 0 <= s["cena_inicio"] <= s["cena_fim"] < n
    ]
    if max_shorts is not None:
        r["shorts"] = r["shorts"][:max_shorts]
    return r


class ClienteClaude:
    def __init__(self, config: Config, cliente: Any = None):
        if cliente is None:
            import anthropic  # dependência opcional: pip install '.[real]'

            cliente = anthropic.Anthropic()
        self._c = cliente
        self._cfg = config

    # --- chamada genérica -------------------------------------------------------------------
    def _chamar(self, prompt: str, *, max_tokens: int, esquema: dict | None = None, web: bool = False) -> RespostaClaude:
        import anthropic

        params: dict[str, Any] = {
            "model": self._cfg.modelo,
            "max_tokens": max_tokens,
            "system": SYSTEM,
            "output_config": {"effort": self._cfg.esforco},
        }
        if esquema:
            params["output_config"]["format"] = {"type": "json_schema", "schema": esquema}
        if web:
            params["tools"] = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
        if self._cfg.fallback:
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"

        mensagens: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        custo, fontes, textos = 0.0, [], []
        try:
            for _ in range(MAX_CONTINUACOES + 1):
                with self._c.beta.messages.stream(messages=mensagens, **params) as fluxo:
                    resp = fluxo.get_final_message()
                custo += self._custo(resp)
                fontes += self._fontes(resp)
                if resp.stop_reason == "refusal":
                    raise ErroDeIA("o modelo recusou a solicitação")
                if resp.stop_reason == "max_tokens":
                    raise ErroDeIA("resposta cortada em max_tokens")
                textos += [b.text for b in resp.content if b.type == "text"]
                if resp.stop_reason != "pause_turn":
                    break
                # busca web demorou: reenvia o turno parcial e o servidor retoma sozinho
                mensagens = [mensagens[0], {"role": "assistant", "content": resp.content}]
            else:
                raise ErroDeIA("busca na web não terminou após várias continuações")
        except anthropic.RateLimitError as e:
            espera = e.response.headers.get("retry-after", "") if getattr(e, "response", None) is not None else ""
            raise LimiteAtingido(timedelta(seconds=int(espera)) if espera.isdigit() else None,
                                 "limite de uso do Claude") from e
        return RespostaClaude("".join(textos), custo * self._cfg.cotacao, list(dict.fromkeys(fontes)))

    def _custo(self, resp: Any) -> float:
        entrada, saida = PRECOS.get(self._cfg.modelo, (4.0, 20.0))
        u = resp.usage
        custo = (u.input_tokens * entrada + u.output_tokens * saida) / 1_000_000
        uso_servidor = getattr(u, "server_tool_use", None)
        buscas = getattr(uso_servidor, "web_search_requests", 0) or 0
        return custo + buscas * CUSTO_BUSCA_WEB

    @staticmethod
    def _fontes(resp: Any) -> list[str]:
        urls = []
        for b in resp.content:
            if b.type == "web_search_tool_result" and isinstance(b.content, list):  # erro vem como objeto
                urls += [r.url for r in b.content if getattr(r, "url", None)]
        return urls

    # --- etapas -----------------------------------------------------------------------------
    def pesquisar(self, tema: str, nicho: str, perfil: Perfil | None = None) -> RespostaClaude:
        prompt = (
            f"{descrever_canal(nicho, perfil or Perfil())}\nTema do vídeo: {tema}\n\n"
            "Pesquise na web e entregue um dossiê em português para o roteirista: fatos verificados "
            "(com datas e números), contexto, pontos polêmicos ou debatidos, curiosidades que prendem "
            "a atenção e erros comuns sobre o tema. Dê preferência a fontes oficiais e recentes e separe com clareza "
            "o que é CONFIRMADO oficialmente do que é rumor, vazamento ou especulação (marque cada item). "
            "Termine com a lista de fontes usadas."
        )
        return self._chamar(prompt, max_tokens=8000, web=True)

    def roteirizar(self, tema: str, nicho: str, dossie: str, perfil: Perfil | None = None) -> tuple[dict[str, Any], float]:
        perfil = perfil or Perfil()
        n = perfil.cenas or self._cfg.cenas
        n_shorts = 3 if perfil.shorts is None else perfil.shorts
        estilo = (f"- O estilo visual do canal é «{perfil.estilo_visual}» e será aplicado automaticamente a toda imagem; "
                  "nos `prompt_imagem` e nas thumbnails descreva só o conteúdo (cena, personagens, ação), de forma compatível com esse estilo.\n"
                  ) if perfil.estilo_visual else ""
        prompt = (
            f"{descrever_canal(nicho, perfil)}\nTema: {tema}\n\nDossiê de pesquisa:\n{dossie}\n\n"
            f"Escreva o vídeo em {n} cenas, em português do Brasil, tom envolvente e claro. Use só fatos do dossiê.\n"
            f"{estilo}"
            "- cenas: cada uma com `narracao` (70 a 110 palavras, texto corrido para ser falado, sem "
            "marcações) e `prompt_imagem` (descrição visual em inglês, estilo ilustração cinematográfica "
            "consistente entre as cenas, sem texto escrito na imagem).\n"
            "- titulos: 3 opções, com no máximo 70 caracteres, atraentes mas honestas.\n"
            "- descricao: descrição do vídeo para o YouTube.\n"
            "- thumbnails: 3 prompts de imagem em inglês, composição forte, um assunto central, "
            "espaço livre para texto; sem texto escrito na imagem.\n"
            + ("- shorts: devolva uma lista vazia (este canal não publica shorts).\n" if n_shorts == 0 else
               f"- shorts: {n_shorts} trecho(s) independente(s) e autoexplicativo(s), cada um com `titulo` e o intervalo "
               f"de cenas (`cena_inicio` e `cena_fim`, índices a partir de 0, até {n - 1}, inclusive; no "
               "máximo 2 cenas por short).\n")
            + "- Só trate como fato o que o dossiê marca como confirmado; rumores e teorias devem ser ditos como rumores e teorias."
        )
        resp = self._chamar(prompt, max_tokens=32000, esquema=ESQUEMA_ROTEIRO)
        try:
            return validar_roteiro(json.loads(resp.texto), n_shorts), resp.custo
        except json.JSONDecodeError as e:
            raise ErroDeIA(f"roteiro não veio em JSON válido: {e}") from e
