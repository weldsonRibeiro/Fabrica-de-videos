"""Relatório de backtest em dados reais: período completo e 'últimos N meses', calibração e um veredito franco."""
from __future__ import annotations

import math
from datetime import datetime, timezone

from .backtest import Config, Resultado, _bootstrap, comparar_prep, preparar
from .dados import Vela, contar_lacunas, preencher_lacunas
from .leitores import Leitor


def _limpo(x):
    return None if isinstance(x, float) and (x != x or math.isinf(x)) else x


def _estat(eq: list[float], passo: int) -> tuple[float, float]:
    rets = [b / a - 1 for a, b in zip(eq, eq[1:])]
    if len(rets) < 2:
        return 0.0, 0.0
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    pico, dd = eq[0], 0.0
    for e in eq:
        pico = max(pico, e)
        dd = max(dd, 1 - e / pico)
    return (m / sd * math.sqrt(365 * 86400 / passo) if sd > 0 else 0.0), dd


def _resumo(nome, retorno, buy_hold, sharpe, dd, trades, expo=None) -> dict:
    ic, pv = _bootstrap([t["ret_capital"] for t in trades])
    return {"nome": nome, "retorno": retorno, "buy_hold": buy_hold, "sharpe": sharpe, "max_dd": dd, "operacoes": len(trades),
            "exposicao": expo, "ic95": [_limpo(ic[0]), _limpo(ic[1])], "p_valor": pv,
            "significativo": len(trades) >= 30 and ic[0] > 0}


def resumir(r: Resultado) -> dict:
    return _resumo(r.nome, r.retorno, r.buy_hold, r.sharpe, r.max_dd, r.trades, r.exposicao) | {"desligado": r.desligado}


def recortar(r: Resultado, velas: list[Vela], inicio: int, t_ini: int) -> dict:
    """Mesma execução, olhando só do instante t_ini em diante (o modelo já vinha treinado: é fora da amostra de ajuste)."""
    i0 = next((i for i in range(inicio, len(velas)) if velas[i].t >= t_ini), len(velas) - 1)
    eq = r.equity[i0 - inicio:]
    passo = velas[1].t - velas[0].t
    sharpe, dd = _estat(eq, passo)
    trades = [t for t in r.trades if t["t_entrada"] >= t_ini]
    return _resumo(r.nome, eq[-1] / eq[0] - 1, velas[-1].c / velas[i0].c - 1, sharpe, dd, trades)


def veredito(completo: list[dict], teste: list[dict], meses: int) -> list[str]:
    linhas = []
    achou = [r for r in completo + teste if r["significativo"] and r["retorno"] > 0 and r["nome"].startswith("agentes")]
    if achou:
        linhas.append("Há EVIDÊNCIA ESTATÍSTICA de vantagem em: " + ", ".join(sorted({r["nome"] for r in achou})) +
                      ". É evidência, não prova: confirme com paper trading antes de qualquer dinheiro.")
    else:
        linhas.append("SEM evidência de vantagem após custos neste histórico: o intervalo de confiança do retorno por operação "
                      "inclui zero (ou há poucas operações). O sistema não deve operar dinheiro real com base nisto.")
    base, melhor = completo[0], max(completo, key=lambda r: r["retorno"])
    if melhor["retorno"] < base["buy_hold"]:
        linhas.append(f"Comprar e segurar rendeu {base['buy_hold']:+.1%} no período; nenhuma estratégia testada fez mais que isso.")
    linhas.append(f"Os últimos {meses} meses são tratados como teste: o código não foi ajustado olhando esses dados.")
    return linhas


def relatorio(velas: list[Vela], leitores: list[Leitor], cfg: Config | None = None, meses_teste: int = 12,
              fonte: str = "", avisos: list[str] | None = None) -> dict:
    cfg = cfg or Config()
    lacunas = contar_lacunas(velas)
    uniformes = preencher_lacunas(velas) if lacunas else velas
    prep = preparar(uniformes, leitores, cfg.horizonte)
    resultados = comparar_prep(prep, leitores, cfg)
    t_ini = uniformes[-1].t - meses_teste * 30 * 86400
    completo = [resumir(r) for r in resultados]
    teste = [recortar(r, uniformes, prep.inicio, t_ini) for r in resultados]
    base = resultados[0]
    passo_amostra = max(1, len(base.equity) // 240)
    ts = [uniformes[prep.inicio + i].t for i in range(0, len(base.equity), passo_amostra)]
    bh0 = uniformes[prep.inicio].c
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fonte": fonte,
        "periodo": {"de": datetime.fromtimestamp(uniformes[0].t, timezone.utc).strftime("%Y-%m-%d"),
                    "ate": datetime.fromtimestamp(uniformes[-1].t, timezone.utc).strftime("%Y-%m-%d"),
                    "velas": len(uniformes), "lacunas_preenchidas": lacunas, "teste_final_a_partir_de": datetime.fromtimestamp(t_ini, timezone.utc).strftime("%Y-%m-%d")},
        "config": {"horizonte": cfg.horizonte, "taxa_bps": cfg.taxa_bps, "slippage_bps": cfg.slippage_bps, "capital": cfg.capital,
                   "leitores": [l.nome for l in leitores]},
        "completo": completo, "meses_teste": meses_teste, "teste": teste,
        "calibracao": base.prob, "veredito": veredito(completo, teste, meses_teste),
        "grafico": {"t": ts, "estrategia": [100 * base.equity[i] / cfg.capital for i in range(0, len(base.equity), passo_amostra)],
                    "buy_hold": [100 * uniformes[prep.inicio + i].c / bh0 for i in range(0, len(base.equity), passo_amostra)]},
        "avisos": avisos or [],
    }
