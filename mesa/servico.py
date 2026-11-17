"""Backtest automático no servidor: baixa o histórico REAL, calcula o relatório e guarda em backtest.json (refaz toda semana)."""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import dados
from .backtest import Config
from .corretora import salvar_json
from .relatorio import relatorio

IDADE_MAX_DIAS = 7


def _estado(pasta: Path, estado: str, mensagem: str = "") -> None:
    print(f"[backtest] {estado}: {mensagem}", flush=True)
    salvar_json(pasta / "backtest.estado.json", {"estado": estado, "mensagem": mensagem,
                                                 "atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def precisa_rodar(pasta: Path, agora: float | None = None, idade_max_dias: int = IDADE_MAX_DIAS) -> bool:
    arq = pasta / "backtest.json"
    return not arq.exists() or (agora or time.time()) - arq.stat().st_mtime > idade_max_dias * 86400


def rodar_uma_vez(pasta: Path | str, fonte: str, simbolo: str, intervalo: str, dias: int, cfg: Config, leitores_fn: Callable[[list], tuple[list, list[str]]],
                  agora: Callable[[], float] = time.time, **kw) -> dict:
    """Baixa `dias` de histórico, roda o relatório e grava. `leitores_fn(velas)` devolve (leitores, avisos)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    _estado(pasta, "baixando", f"baixando {dias} dias de histórico ({fonte})…")
    desde = int(agora()) - dias * 86400
    if fonte == "coinbase":
        velas = dados.baixar_coinbase(simbolo, intervalo, desde, **kw)
    else:
        velas = dados.baixar_binance(simbolo, intervalo, desde, **{k: v for k, v in kw.items() if k == "transporte"})
    dados.validar(velas)
    dados.salvar_csv(velas, pasta / "historico.csv")
    _estado(pasta, "calculando", f"{len(velas)} velas baixadas; calculando o backtest (alguns minutos)…")
    lista, avisos = leitores_fn(velas)
    rel = relatorio(velas, lista, cfg, fonte=f"{fonte}:{simbolo} {intervalo}", avisos=avisos)
    salvar_json(pasta / "backtest.json", rel)
    _estado(pasta, "pronto", f"pronto ({len(velas)} velas)")
    return rel


def iniciar_em_segundo_plano(pasta, fonte, simbolo, intervalo, dias, cfg, leitores_fn, espera_s: float = 3600.0,
                             dormir: Callable[[float], None] = time.sleep, parar: Callable[[], bool] = lambda: False) -> threading.Thread:
    pasta = Path(pasta)

    def laco():
        while not parar():
            if precisa_rodar(pasta):
                try:
                    rodar_uma_vez(pasta, fonte, simbolo, intervalo, dias, cfg, leitores_fn)
                except Exception as erro:  # noqa: BLE001 — erro de rede/API não derruba o vigia; tenta de novo na próxima hora
                    _estado(pasta, "erro", f"{type(erro).__name__}: {erro}")
                    print(f"[backtest] erro: {erro}\n{traceback.format_exc(limit=2)}", flush=True)
            dormir(espera_s)

    t = threading.Thread(target=laco, daemon=True, name="backtest-automatico")
    t.start()
    return t
