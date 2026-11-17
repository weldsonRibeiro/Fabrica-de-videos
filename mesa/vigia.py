"""O vigia: monitora o Bitcoin 24 horas com dados reais, roda os agentes a cada vela fechada e opera NA SIMULAÇÃO.

A cada checagem (padrão 60 s): lê o preço, aplica stop/prazo à posição simulada e atualiza o guarda de risco.
A cada vela fechada: roda os agentes, grava o sinal no diário e, se o risco permitir, abre uma posição simulada.
O estado fica em disco: se o programa reiniciar, continua de onde parou.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .backtest import Config
from .corretora import CorretoraSimulada, salvar_json
from .dados import Vela, ler_csv, salvar_csv
from .fontes import Fonte
from .leitores import Leitor
from .risco import GuardaRisco
from .sinal import gerar_sinal, registrar

HISTORICO_MAX = 5000      # velas mantidas (≈ 7 meses de velas de 1 h): limita o custo de cada recálculo


class Vigia:
    def __init__(self, fonte: Fonte, leitores: list[Leitor], cfg: Config, pasta: Path | str, corretora: CorretoraSimulada | None = None,
                 atualizadores: list[Callable[[], None]] | None = None):
        self.fonte, self.leitores, self.cfg = fonte, leitores, cfg
        self.atualizadores = atualizadores or []
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.corretora = corretora or CorretoraSimulada(cfg.capital, cfg.taxa_bps, cfg.slippage_bps)
        self.guarda = GuardaRisco(cfg.risco, cfg.capital)
        self.velas: list[Vela] = []
        self.ultimo_sinal_t = 0
        self.ultimo_preco = 0.0
        self._carregar()

    # --- estado em disco ------------------------------------------------------------------------
    @property
    def _estado(self) -> Path:
        return self.pasta / "estado.json"

    def _carregar(self) -> None:
        hist = self.pasta / "velas.csv"
        if hist.exists():
            self.velas = ler_csv(hist)
        if self._estado.exists():
            d = json.loads(self._estado.read_text(encoding="utf-8"))
            self.corretora.de_dict(d["corretora"])
            self.guarda.de_dict(d["guarda"])
            self.ultimo_sinal_t = d.get("ultimo_sinal_t", 0)

    def _salvar(self, agora: float, ultimo_sinal: dict | None = None) -> None:
        d = {"atualizado_em": datetime.fromtimestamp(agora, timezone.utc).isoformat(timespec="seconds"),
             "modo": "SIMULAÇÃO (nenhuma ordem real é enviada)", "preco": self.ultimo_preco,
             "equity": round(self.corretora.equity(self.ultimo_preco or 0), 2), "capital_inicial": self.corretora.capital_inicial,
             "ultimo_sinal_t": self.ultimo_sinal_t, "corretora": self.corretora.para_dict(), "guarda": self.guarda.para_dict()}
        if ultimo_sinal is not None:
            d["ultimo_sinal"] = ultimo_sinal
        elif self._estado.exists():
            d["ultimo_sinal"] = json.loads(self._estado.read_text(encoding="utf-8")).get("ultimo_sinal")
        salvar_json(self._estado, d)

    def _evento(self, agora: float, texto: str) -> str:
        linha = f"{datetime.fromtimestamp(agora, timezone.utc):%Y-%m-%d %H:%M:%S} UTC  {texto}"
        with open(self.pasta / "eventos.log", "a", encoding="utf-8") as f:
            f.write(linha + "\n")
        return linha

    # --- um ciclo -------------------------------------------------------------------------------
    def passo(self, agora: float | None = None) -> list[str]:
        agora = agora if agora is not None else time.time()
        eventos: list[str] = []
        preco = self.fonte.preco()
        self.ultimo_preco = preco

        trade = self.corretora.marcar(int(agora), preco)           # stop / prazo da posição aberta
        if trade:
            eventos.append(self._evento(agora, f"FECHOU (simulado) por {trade['motivo']}: {trade['ret_capital']:+.2%} do capital"))
        self.guarda.atualizar(int(agora), self.corretora.equity(preco))

        novas = self.fonte.velas(HISTORICO_MAX if not self.velas else 50, agora)
        if novas:
            por_t = {v.t: v for v in self.velas}
            por_t.update({v.t: v for v in novas})
            self.velas = sorted(por_t.values(), key=lambda v: v.t)[-HISTORICO_MAX:]
            salvar_csv(self.velas, self.pasta / "velas.csv")

        ultima = self.velas[-1] if self.velas else None
        if ultima and ultima.t > self.ultimo_sinal_t:               # vela nova fechada: hora de pensar
            for atualizar in self.atualizadores:                    # séries de fora (medo e ganância, funding): falha não derruba
                try:
                    atualizar()
                except Exception as erro:  # noqa: BLE001
                    eventos.append(self._evento(agora, f"aviso: não consegui atualizar um dado externo ({erro})"))
            s = gerar_sinal(self.velas, self.leitores, self.cfg)
            registrar(self.pasta / "diario.jsonl", s)
            self.ultimo_sinal_t = ultima.t
            if s["p"] is None:
                eventos.append(self._evento(agora, f"sinal: {s['motivo']}"))
            else:
                eventos.append(self._evento(agora, f"vela {datetime.fromtimestamp(ultima.t, timezone.utc):%d/%m %H:%M} · p(alta)={s['p']:.2f} · {s['motivo']}"))
            if s.get("direcao"):
                ok, motivo = self.guarda.pode_operar(self.corretora.equity(preco))
                if not ok:
                    eventos.append(self._evento(agora, f"ordem BLOQUEADA pelo risco: {motivo}"))
                elif self.corretora.abrir(int(agora), preco, s["direcao"], s["fracao"], s["stop_pct"], s["p"],
                                          int(agora) + self.cfg.horizonte * self.fonte.passo):
                    eventos.append(self._evento(agora, f"ABRIU (simulado) {'compra' if s['direcao'] > 0 else 'venda'} de {s['fracao']:.1%} do capital a {preco:,.2f}"))
            self._salvar(agora, s)
        else:
            self._salvar(agora)
        return eventos

    def rodar(self, checagem_s: float = 60.0, parar: Callable[[], bool] = lambda: False, dormir: Callable[[float], None] = time.sleep) -> None:
        """Laço de 24 horas. Erro de rede não derruba: registra e tenta de novo."""
        while not parar():
            try:
                for e in self.passo():
                    print(e, flush=True)
            except Exception as erro:  # noqa: BLE001
                print(self._evento(time.time(), f"erro (tentando de novo): {erro}"), flush=True)
            dormir(checagem_s)
