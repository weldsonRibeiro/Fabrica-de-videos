"""Linha de comando: `python -m fabrica ...`"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from .armazem import Armazem
from .jogo import Carteira
from .maestro import Maestro, aprovar
from .modelos import Canal
from .pipeline import Pipeline
from .provedores.falso import ProvedorFalso, PublicadorFalso


def _maestro(args: argparse.Namespace) -> Maestro:
    armazem = Armazem(args.dados)
    canais = [Canal.de_dict(c) for c in json.loads(Path(args.canais).read_text(encoding="utf-8"))]
    return Maestro(armazem, Pipeline(_provedor(args), armazem), canais, PublicadorFalso())


def _provedor(args: argparse.Namespace):
    if args.provedor == "real":
        from .config import Config, ErroDeConfiguracao
        from .provedores.real import ProvedorReal

        try:
            return ProvedorReal(Config.do_ambiente())
        except (ErroDeConfiguracao, ImportError) as erro:
            raise SystemExit(f"provedor real indisponível: {erro}")
    return ProvedorFalso()


def _agora(texto: str | None) -> datetime:
    return datetime.fromisoformat(texto) if texto else datetime.now().replace(microsecond=0)


def principal(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fabrica", description="Fábrica de vídeos com IA")
    p.add_argument("--dados", default="dados", help="pasta do estado (padrão: dados)")
    p.add_argument("--canais", default="canais.example.json", help="arquivo de canais")
    p.add_argument("--provedor", choices=["falso", "real"], default="falso",
                   help="falso = simulação sem custo; real = Claude + voz + imagem + ffmpeg (veja .env.example)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("agenda", help="monta a agenda de um dia")
    s.add_argument("--dia", default=None, help="AAAA-MM-DD (padrão: hoje)")

    s = sub.add_parser("tick", help="uma batida do maestro (rode de minuto em minuto, via cron)")
    s.add_argument("--agora", default=None, help="ISO, p/ simular o relógio")

    sub.add_parser("status", help="lista os vídeos")

    s = sub.add_parser("aprovar", help="aprova um vídeo pronto")
    s.add_argument("video")
    s.add_argument("--titulo", type=int, default=0)
    s.add_argument("--thumbnail", type=int, default=0)
    s.add_argument("--publicar-em", required=True, help="ISO, ex.: 2026-11-16T18:00")

    s = sub.add_parser("views", help="registra as views de um vídeo (vira moeda)")
    s.add_argument("video")
    s.add_argument("total", type=int)

    sub.add_parser("carteira", help="saldo da empresa no jogo")

    args = p.parse_args(argv)
    armazem = Armazem(args.dados)

    if args.cmd == "agenda":
        dia = date.fromisoformat(args.dia) if args.dia else date.today()
        for v in _maestro(args).montar_agenda(dia):
            print(f"{v.producao_em:%H:%M}  {v.id}  {v.tema}")
    elif args.cmd == "tick":
        for v in _maestro(args).tick(_agora(args.agora)):
            print(f"{v.id}: {v.status.value}")
    elif args.cmd == "status":
        for v in armazem.listar_videos():
            extra = f" (retoma {v.retomar_em:%d/%m %H:%M})" if v.retomar_em else ""
            print(f"{v.id:<28} {v.status.value:<22} custo {v.custo:>6.2f}{extra}")
    elif args.cmd == "aprovar":
        v = aprovar(armazem, args.video, args.titulo, args.thumbnail, datetime.fromisoformat(args.publicar_em))
        print(f"aprovado: {v.escolha['titulo']} → {v.escolha['publicar_em']}")
    elif args.cmd == "views":
        carteira = Carteira.carregar(armazem)
        ganhou = carteira.registrar_views(args.video, args.total)
        carteira.salvar(armazem)
        print(f"+{ganhou:.2f} moedas")
    elif args.cmd == "carteira":
        c = Carteira.carregar(armazem)
        print(f"saldo: {c.saldo:.2f}")
    return 0
