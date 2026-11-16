"""`fabrica doctor`: confere o que falta antes de rodar. Nunca imprime valores de chaves."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

OK, AVISO, ERRO = "ok", "aviso", "erro"
Resultado = tuple[str, str]


def verificar(
    *, canais: str, dados: str, saida: str, provedor: str, publicador: str,
    env: Mapping[str, str] | None = None, which: Callable[[str], str | None] = shutil.which,
) -> list[Resultado]:
    env = os.environ if env is None else env
    r: list[Resultado] = []
    add = lambda nivel, texto: r.append((nivel, texto))  # noqa: E731

    add(OK if sys.version_info >= (3, 10) else ERRO, f"Python {sys.version_info.major}.{sys.version_info.minor} (precisa de 3.10+)")

    try:
        ZoneInfo(env.get("FABRICA_FUSO", "America/Sao_Paulo"))
        add(OK, f"Fuso horário: {env.get('FABRICA_FUSO', 'America/Sao_Paulo')}")
    except ZoneInfoNotFoundError:
        add(ERRO, f"FABRICA_FUSO inválido: {env.get('FABRICA_FUSO')}")

    ids: list[str] = []
    arquivo = Path(canais)
    if not arquivo.is_file():
        add(ERRO, f"Arquivo de canais não existe: {canais} (copie canais.example.json e edite)")
    else:
        try:
            lista = json.loads(arquivo.read_text(encoding="utf-8"))
            problemas = []
            for c in lista:
                if not re.fullmatch(r"\d{2}:\d{2}", str(c.get("inicio_producao", ""))):
                    problemas.append(f"{c.get('id', '?')}: inicio_producao deve ser HH:MM")
                if not c.get("temas"):
                    problemas.append(f"{c.get('id', '?')}: sem temas")
                if not c.get("id") or not c.get("nome"):
                    problemas.append("canal sem id/nome")
            VOZES = {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"}
            CAMPOS = {"voz", "estilo_voz", "tom", "publico", "estilo_visual", "evitar", "cenas", "categoria_youtube", "idioma", "shorts"}
            for c in lista:
                perfil = c.get("perfil") or {}
                nome = c.get("id", "?")
                desconhecidos = sorted(set(perfil) - CAMPOS)
                if desconhecidos:
                    problemas.append(f"{nome}: campo(s) de perfil desconhecido(s): {', '.join(desconhecidos)}")
                if perfil.get("cenas") not in (None, 0) and not (isinstance(perfil["cenas"], int) and 1 <= perfil["cenas"] <= 30):
                    problemas.append(f"{nome}: perfil.cenas deve ser um número de 1 a 30")
                if perfil.get("shorts") is not None and not (isinstance(perfil["shorts"], int) and 0 <= perfil["shorts"] <= 5):
                    problemas.append(f"{nome}: perfil.shorts deve ser um número de 0 a 5")
                if perfil.get("categoria_youtube") and not str(perfil["categoria_youtube"]).isdigit():
                    problemas.append(f"{nome}: perfil.categoria_youtube deve ser o número da categoria (ex.: 27)")
                if perfil.get("voz") and perfil["voz"] not in VOZES:
                    r.append((AVISO, f"Canal '{nome}': voz '{perfil['voz']}' não está na lista conhecida ({', '.join(sorted(VOZES))}) — confira"))
            ids = [c["id"] for c in lista if c.get("id")]
            if publicador == "youtube":
                uploads = sum(1 + (3 if (c.get("perfil") or {}).get("shorts") is None else (c.get("perfil") or {})["shorts"]) for c in lista)
                unidades = uploads * 1600 + len(lista) * 50
                if unidades > 10000:
                    r.append((AVISO, f"Cota do YouTube: {uploads} uploads/dia ≈ {unidades:,} unidades, acima das 10.000 da cota padrão "
                                     f"(≈ 6 uploads/dia) — reduza `perfil.shorts` (0 poupa a cota) ou peça aumento de cota ao Google".replace(",", ".")))
            add(ERRO if problemas else OK, f"{len(lista)} canal(is) em {canais}" + (": " + "; ".join(problemas) if problemas else ""))
            if arquivo.name == "canais.example.json":
                add(AVISO, "Usando o canais.example.json de exemplo — copie para canais.json e coloque os SEUS canais")
        except (ValueError, AttributeError, TypeError) as e:
            add(ERRO, f"{canais} inválido: {e}")

    for nome, pasta in (("dados", dados), ("saída", saida)):
        p = Path(pasta)
        try:
            p.mkdir(parents=True, exist_ok=True)
            teste = p / ".escrita"
            teste.write_text("ok")
            teste.unlink()
            add(OK, f"Pasta de {nome} gravável: {pasta}")
        except OSError as e:
            add(ERRO, f"Sem permissão na pasta de {nome} ({pasta}): {e}")

    chave = env.get("FABRICA_PAINEL_CHAVE", "")
    add(OK if len(chave) >= 16 else ERRO, "Chave do painel (FABRICA_PAINEL_CHAVE)" + ("" if len(chave) >= 16 else " ausente ou com menos de 16 caracteres"))

    ffmpeg = which("ffmpeg") and which("ffprobe")
    if provedor == "real":
        add(OK if ffmpeg else ERRO, "ffmpeg/ffprobe instalados" if ffmpeg else "ffmpeg/ffprobe não encontrados (necessários para montar o vídeo)")
        try:
            import anthropic  # noqa: F401
            add(OK, "SDK do Claude instalado")
        except ImportError:
            add(ERRO, "SDK do Claude ausente — rode: pip install '.[real]'")
        if env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN"):
            add(OK, "Chave do Claude (ANTHROPIC_API_KEY) definida")
        else:
            add(AVISO, "ANTHROPIC_API_KEY ausente — vale só se você usa um perfil `ant auth login`")
        add(OK if env.get("OPENAI_API_KEY") else ERRO, "Chave de voz/imagem (OPENAI_API_KEY)" + ("" if env.get("OPENAI_API_KEY") else " ausente"))
    else:
        add(AVISO, "Provedor FALSO (simulação, sem custo). Para produzir de verdade: FABRICA_PROVEDOR=real")
        add(OK if ffmpeg else AVISO, "ffmpeg encontrado" if ffmpeg else "ffmpeg não encontrado (só é necessário com o provedor real)")

    if publicador == "youtube":
        faltam = [n for n in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET") if not env.get(n)]
        add(ERRO if faltam else OK, "Credenciais OAuth do YouTube" + (f" ausentes: {', '.join(faltam)}" if faltam else ""))
        for canal in ids:
            var = "YOUTUBE_REFRESH_TOKEN_" + re.sub(r"[^A-Z0-9]", "_", canal.upper())
            add(OK if env.get(var) else ERRO, f"Canal '{canal}' autorizado" if env.get(var) else
                f"Canal '{canal}' sem token ({var}) — rode no SEU computador: python -m fabrica youtube-autorizar --canal {canal}")
    else:
        add(AVISO, "Publicador FALSO: nada vai para o YouTube. Para publicar de verdade: FABRICA_PUBLICADOR=youtube")
    return r


def imprimir(resultados: list[Resultado]) -> int:
    icones = {OK: "✅", AVISO: "⚠️ ", ERRO: "❌"}
    for nivel, texto in resultados:
        print(f"{icones[nivel]} {texto}")
    erros = sum(1 for n, _ in resultados if n == ERRO)
    avisos = sum(1 for n, _ in resultados if n == AVISO)
    print(f"\n{'Tudo pronto para rodar.' if not erros else f'{erros} problema(s) a resolver antes de rodar.'}" + (f" ({avisos} aviso(s))" if avisos else ""))
    return 1 if erros else 0
