"""Sinal do momento + diário: o 'paper trading' (ordens simuladas) para conferir o sistema ao vivo, sem dinheiro."""
from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

from .agregador import AgregadorLogistico, AgregadorMedia, linha
from .backtest import Config, _bootstrap, preparar
from .dados import Vela
from .leitores import Leitor, vol_por_vela
from .risco import avaliar_entrada


def gerar_sinal(velas: list[Vela], leitores: list[Leitor], cfg: Config) -> dict:
    """Recomendação simulada para a ÚLTIMA vela fechada. Treina só com o que já tem resultado conhecido."""
    H = cfg.horizonte
    k = len(velas) - 1
    ls = [l.ler(velas[max(0, k + 1 - l.janela): k + 1]) for l in leitores]
    base = {"t": velas[k].t, "preco": velas[k].c, "horizonte": H,
            "leituras": [{"leitor": l.nome, "p": round(l.p, 4), "conf": round(l.conf, 3), "nota": l.nota} for l in ls]}
    if cfg.agregador == "media":                       # não precisa treinar: só as leituras da última vela
        agg, linha_k = AgregadorMedia(cfg.usar), linha(ls)
        veto_k, vol_k = any(l.veto for l in ls), vol_por_vela(velas[-49:])
    else:
        prep = preparar(velas, leitores, H)
        linha_k, veto_k, vol_k = prep.X[k], prep.veto[k], prep.vol[k]
        js = [j for j in prep.y if j + H <= k][-cfg.treino_max:]
        if len(js) < cfg.treino_min:
            return {**base, "p": None, "direcao": 0, "motivo": f"dados insuficientes para treinar ({len(js)}/{cfg.treino_min} amostras)"}
        agg = AgregadorLogistico(cfg.usar)
        agg.ajustar([prep.X[j] for j in js], [prep.y[j] for j in js])
    p = agg.prob(linha_k)
    if veto_k:
        return {**base, "p": round(p, 4), "direcao": 0, "motivo": "vetado pelo leitor de regime (volatilidade explosiva)"}
    d = avaliar_entrada(p, vol_k, H, cfg.taxa_bps, cfg.slippage_bps, cfg.risco)
    return {**base, "p": round(p, 4), "direcao": d.direcao, "fracao": round(d.fracao, 4), "stop_pct": round(d.stop_pct, 4),
            "ev": round(d.ev, 5), "motivo": d.motivo or ("comprar (simulado)" if d.direcao > 0 else "vender (simulado)")}


def registrar(diario: Path, sinal: dict) -> bool:
    """Grava no diário (um sinal por vela). Devolve False se esta vela já estava registrada."""
    if diario.exists() and any(json.loads(l)["t"] == sinal["t"] for l in diario.read_text(encoding="utf-8").splitlines() if l):
        return False
    with open(diario, "a", encoding="utf-8") as f:
        f.write(json.dumps(sinal, ensure_ascii=False) + "\n")
    return True


def avaliar(diario: Path, velas: list[Vela], cfg: Config) -> dict:
    """Confere os sinais passados contra o que o preço de fato fez (uma posição por vez, com custos)."""
    por_t = {v.t: i for i, v in enumerate(velas)}
    sinais = sorted((json.loads(l) for l in diario.read_text(encoding="utf-8").splitlines() if l), key=lambda s: s["t"])
    livre_ate, trades, pendentes = -1, [], 0
    custo = 2 * (cfg.taxa_bps + cfg.slippage_bps) / 1e4
    for s in sinais:
        if not s.get("direcao") or s["t"] not in por_t or s["t"] < livre_ate:
            continue
        k = por_t[s["t"]]
        if k + s["horizonte"] >= len(velas):
            pendentes += 1
            continue
        entrada, saida = velas[k + 1].o, velas[k + s["horizonte"]].c
        bruto = (saida / entrada - 1) * s["direcao"]
        trades.append((bruto - custo) * s["fracao"])
        livre_ate = velas[k + s["horizonte"]].t
    ic, pv = _bootstrap(trades)
    return {"sinais": len(sinais), "operacoes_resolvidas": len(trades), "pendentes": pendentes,
            "retorno_medio_por_operacao": (sum(trades) / len(trades)) if trades else None,
            "retorno_total": math.prod(1 + t for t in trades) - 1 if trades else None, "ic95": ic, "p_valor": pv}
