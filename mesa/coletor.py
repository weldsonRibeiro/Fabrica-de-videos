"""Coletor 24 h: junta, no SEU computador, os dados de curto prazo — velas de 1 minuto e o melhor preço de compra e venda
(com o spread). Serve de matéria-prima para o teste de curto prazo (H2) e mostra o custo REAL de cruzar o spread."""
from __future__ import annotations

import csv
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .corretora import salvar_json
from .dados import Vela, ler_csv, salvar_csv
from .fontes import Fonte


class Coletor:
    def __init__(self, fonte, pasta: Path | str):
        if fonte.passo != 60:
            raise ValueError("o coletor usa velas de 1 minuto")
        self.fonte, self.pasta = fonte, Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.velas_csv, self.livro_csv = self.pasta / "velas1m.csv", self.pasta / "livro.csv"
        self.ultimo_t = ler_csv(self.velas_csv)[-1].t if self.velas_csv.exists() else 0
        if not self.livro_csv.exists():
            self.livro_csv.write_text("t,bid,ask,bid_qty,ask_qty\n", encoding="utf-8")

    def passo(self, agora: float | None = None) -> dict:
        agora = agora if agora is not None else time.time()
        bid, ask, bq, aq = self.fonte.livro()
        with open(self.livro_csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([int(agora), bid, ask, bq, aq])
        novas = [v for v in self.fonte.velas(30, agora) if v.t > self.ultimo_t]
        if novas:
            existente = ler_csv(self.velas_csv) if self.velas_csv.exists() else []
            salvar_csv(existente + novas, self.velas_csv)
            self.ultimo_t = novas[-1].t
        return {"spread_bps": (ask - bid) / ((ask + bid) / 2) * 1e4, "velas_novas": len(novas)}

    def rodar(self, livro_cada_s: float = 10.0, parar: Callable[[], bool] = lambda: False, dormir: Callable[[float], None] = time.sleep) -> None:
        while not parar():
            try:
                r = self.passo()
                if r["velas_novas"]:
                    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC  +{r['velas_novas']} vela(s) · spread {r['spread_bps']:.3f} bps", flush=True)
            except Exception as erro:  # noqa: BLE001 — rede instável não derruba a coleta
                print(f"erro (tentando de novo): {erro}", flush=True)
            dormir(livro_cada_s)


def resumo(pasta: Path | str) -> dict:
    """O que já foi coletado e quanto custa, de fato, cruzar o spread."""
    pasta = Path(pasta)
    out: dict = {"pasta": str(pasta)}
    livro = pasta / "livro.csv"
    if livro.exists():
        spreads, ts = [], []
        with open(livro, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                b, a = float(r["bid"]), float(r["ask"])
                spreads.append((a - b) / ((a + b) / 2) * 1e4)
                ts.append(int(r["t"]))
        if spreads:
            q = sorted(spreads)
            out["livro"] = {"fotos": len(spreads), "dias": round((ts[-1] - ts[0]) / 86400, 2), "spread_bps_medio": statistics.fmean(spreads),
                            "spread_bps_mediana": statistics.median(spreads), "spread_bps_p95": q[int(0.95 * (len(q) - 1))], "spread_bps_max": q[-1]}
    velas = pasta / "velas1m.csv"
    if velas.exists():
        v = ler_csv(velas)
        out["velas"] = {"n": len(v), "dias": round((v[-1].t - v[0].t) / 86400, 2) if len(v) > 1 else 0,
                        "de": datetime.fromtimestamp(v[0].t, timezone.utc).strftime("%Y-%m-%d %H:%M"), "ate": datetime.fromtimestamp(v[-1].t, timezone.utc).strftime("%Y-%m-%d %H:%M")}
    return out
