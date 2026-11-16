"""Relógio da fábrica no fuso do dono — o servidor pode estar em UTC, a agenda é no seu horário."""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

PADRAO = "America/Sao_Paulo"


def nome_do_fuso() -> str:
    return os.environ.get("FABRICA_FUSO", PADRAO)


def agora_local() -> datetime:
    """Hora de agora no fuso configurado, sem informação de fuso (como a agenda guarda)."""
    return datetime.now(ZoneInfo(nome_do_fuso())).replace(microsecond=0, tzinfo=None)
