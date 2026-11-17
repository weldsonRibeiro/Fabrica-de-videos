"""Hipóteses PRÉ-REGISTRADAS: parâmetros e critério de aprovação fixados no código, antes de ver qualquer resultado.

Hipótese H1 (funding): "o funding dos perpétuos (compradores alavancados lotando um lado) carrega informação sobre o
retorno das próximas 24 h do Bitcoin que os indicadores de preço não têm".

O protocolo NÃO tem parâmetros de linha de comando de propósito: horizonte, custos, número de testes e critérios são
constantes. Se o resultado for REPROVADO, a hipótese está encerrada. Mudar um número e rodar de novo é o que faz alguém
'encontrar' vantagem no acaso; para testar outra ideia, escreva outra hipótese ANTES de rodar.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .backtest import Config, Resultado, preparar, rodar
from .dados import Vela
from .externos import Serie
from .leitores import Funding, leitores_padrao
from .relatorio import resumir

PROTOCOLO_H1 = {
    "hipotese": "H1: o funding carrega informação sobre o retorno das próximas 24 h do Bitcoin além dos indicadores de preço",
    "horizonte": 24, "taxa_bps": 10.0, "slippage_bps": 5.0, "n_testes": 2, "alfa": 0.05, "min_operacoes": 30,
    "testes": ["só funding", "agentes + funding (logística)"],
    "aprovacao": [
        "operações ≥ 30",
        "p-valor (bootstrap, unilateral) ≤ 0,05 ÷ 2 = 0,025",
        "retorno líquido > 0 no período inteiro E em cada metade do período (primeira e segunda)",
        "só para 'agentes + funding': Brier < 0,2500 E menor que o Brier dos mesmos agentes SEM funding",
    ],
    "se_reprovar": "hipótese encerrada: não ajustar nem repetir com outros números",
    "se_aprovar": "vira candidata a paper trading ao vivo (≥ 8 semanas e ≥ 30 operações) — NÃO a dinheiro real",
}


def _metades(r: Resultado) -> tuple[float, float]:
    m = len(r.equity) // 2
    return r.equity[m] / r.equity[0] - 1, r.equity[-1] / r.equity[m] - 1


def avaliar_funding(velas: list[Vela], serie: Serie) -> dict:
    P = PROTOCOLO_H1
    cfg = Config(horizonte=P["horizonte"], taxa_bps=P["taxa_bps"], slippage_bps=P["slippage_bps"])
    base = rodar(preparar(velas, leitores_padrao(), cfg.horizonte), replace(cfg, agregador="logistico"), "agentes sem funding")
    solo = rodar(preparar(velas, [Funding(serie)], cfg.horizonte), replace(cfg, agregador="media"), "só funding")
    comb = rodar(preparar(velas, leitores_padrao([Funding(serie)]), cfg.horizonte), replace(cfg, agregador="logistico"), "agentes + funding (logística)")
    alfa = P["alfa"] / P["n_testes"]
    avaliados = []
    for r in (solo, comb):
        h1, h2 = _metades(r)
        res = resumir(r)
        criterios = {
            "operações ≥ 30": res["operacoes"] >= P["min_operacoes"],
            f"p ≤ {alfa:.3f}": res["p_valor"] <= alfa,
            "retorno > 0 (inteiro e nas duas metades)": res["retorno"] > 0 and h1 > 0 and h2 > 0,
        }
        if r is comb:
            criterios["Brier < 0,25 e melhor que sem funding"] = bool(r.prob.get("n")) and r.prob["brier"] < 0.25 and r.prob["brier"] < base.prob["brier"]
        avaliados.append({"nome": r.nome, "retorno": res["retorno"], "metade_1": h1, "metade_2": h2, "operacoes": res["operacoes"],
                          "p_valor": res["p_valor"], "ic95": res["ic95"], "brier": r.prob.get("brier"), "criterios": criterios,
                          "passou": all(criterios.values())})
    aprovado = any(a["passou"] for a in avaliados)
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "protocolo": P,
        "dados": {"velas": len(velas), "de": datetime.fromtimestamp(velas[0].t, timezone.utc).strftime("%Y-%m-%d"),
                  "ate": datetime.fromtimestamp(velas[-1].t, timezone.utc).strftime("%Y-%m-%d"), "pontos_funding": len(serie)},
        "base": {"nome": base.nome, "retorno": base.retorno, "brier": base.prob.get("brier")},
        "buy_hold": base.buy_hold, "avaliados": avaliados, "aprovado": aprovado,
        "veredito": ("APROVADA para paper trading ao vivo (NÃO para dinheiro real): confirme com ≥ 8 semanas e ≥ 30 operações simuladas."
                     if aprovado else "REPROVADA: " + P["se_reprovar"] + "."),
    }


def formatar(v: dict) -> str:
    P, d = v["protocolo"], v["dados"]
    out = [f"{P['hipotese']}", f"dados: {d['velas']} velas ({d['de']} → {d['ate']}) · {d['pontos_funding']} pontos de funding · horizonte {P['horizonte']} h · custo {P['taxa_bps'] + P['slippage_bps']:.0f} bps por lado",
           "critérios de aprovação (fixados antes de rodar): " + "; ".join(P["aprovacao"]),
           f"\nreferência: agentes SEM funding {v['base']['retorno']:+.1%} (Brier {v['base']['brier']:.4f}) · comprar e segurar {v['buy_hold']:+.1%}"]
    for a in v["avaliados"]:
        ic = a["ic95"]
        out.append(f"\n{a['nome']}: retorno {a['retorno']:+.1%} (1ª metade {a['metade_1']:+.1%} · 2ª metade {a['metade_2']:+.1%}) · {a['operacoes']} operações · "
                   f"p={a['p_valor']:.3f} · IC95% por operação [{ic[0]:+.2%} , {ic[1]:+.2%}]" if ic[0] is not None else f"\n{a['nome']}: {a['operacoes']} operações (poucas para concluir)")
        if a.get("brier") is not None:
            out[-1] += f" · Brier {a['brier']:.4f}"
        out += [f"   {'✓' if ok else '✗'} {nome}" for nome, ok in a["criterios"].items()]
    out.append("\nVEREDITO: " + v["veredito"])
    return "\n".join(out)
