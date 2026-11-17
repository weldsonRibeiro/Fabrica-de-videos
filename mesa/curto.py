"""Hipótese H2 (curto prazo), PRÉ-REGISTRADA: "com velas de 1 minuto, os agentes acham operações de 5–60 minutos cujo ganho
BRUTO médio supera o custo de ida e volta — e isso aparece em muitas operações por dia".

Por que existe: ganhar na QUANTIDADE de operações só funciona se o ganho bruto médio por operação for maior que o custo
de entrar e sair. Em vez de apostar que sim, este teste MEDE o ganho bruto (sem custo nenhum) e calcula o *custo de
equilíbrio*: a maior taxa por lado com que a estratégia ainda empata. Depois compara com a SUA taxa real.

Como em H1, o protocolo é fixo no código (horizontes, estratégias, critérios): 4 horizontes × 2 agregadores = 8 testes,
com correção de Bonferroni. Reprovou → encerrada; outra ideia exige outra hipótese escrita ANTES de rodar.
A taxa é um FATO da sua conta (não um botão de ajuste): fica registrada no resultado, e a tabela de sensibilidade
mostra o que aconteceria com taxas menores.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .backtest import Config, Resultado, com_horizonte, preparar, rodar
from .dados import Vela
from .hipotese import _metades
from .leitores import leitores_padrao
from .relatorio import resumir

HORIZONTES = [5, 15, 30, 60]                      # minutos
AGREGADORES = ["logistico", "media"]
TAXA_PADRAO_BPS = 10.0                             # Binance spot, conta nova sem BNB (0,10% por lado); com desconto em BNB seria 7,5
SLIPPAGE_BPS = 1.0
CENARIOS_TAXA_BPS = [10.0, 7.5, 5.0, 2.0, 0.0]     # sensibilidade: o que muda se a taxa fosse outra
PROTOCOLO_H2 = {
    "hipotese": "H2: com velas de 1 minuto, os agentes acham operações de 5–60 min cujo ganho bruto supera o custo, em volume diário alto",
    "horizontes_min": HORIZONTES, "agregadores": AGREGADORES, "n_testes": len(HORIZONTES) * len(AGREGADORES),
    "alfa": 0.05, "min_operacoes": 200, "slippage_bps": SLIPPAGE_BPS,
    "aprovacao": [
        "operações ≥ 200",
        "p-valor (bootstrap, unilateral) ≤ 0,05 ÷ 8 = 0,00625",
        "retorno líquido > 0 no período inteiro E em cada metade",
    ],
    "se_reprovar": "hipótese encerrada: não ajustar nem repetir com outros números",
    "se_aprovar": "vira candidata a paper trading ao vivo (≥ 8 semanas e ≥ 200 operações) — NÃO a dinheiro real",
}


def _config(h: int, agregador: str, taxa_bps: float, slip_bps: float) -> Config:
    # janelas de treino em minutos (≈ 1 dia de retreino, até ~7 dias de histórico) — fixas, não são botões
    return Config(horizonte=h, agregador=agregador, retreino=1440, treino_min=1000, treino_max=10_000, taxa_bps=taxa_bps, slippage_bps=slip_bps)


def _dias(velas: list[Vela]) -> float:
    return max(1e-9, (velas[-1].t - velas[0].t) / 86400)


def avaliar_curto(velas: list[Vela], taxa_bps: float = TAXA_PADRAO_BPS, min_velas: int = 20_160) -> dict:
    P = PROTOCOLO_H2
    if len(velas) < 2 or velas[1].t - velas[0].t != 60:
        raise ValueError("H2 usa velas de 1 minuto (baixe com --intervalo 1m)")
    if len(velas) < min_velas:
        raise ValueError(f"poucos dados: {len(velas)} velas de 1 min; são necessárias ≥ {min_velas} (≈ {min_velas / 1440:.0f} dias)")
    base = preparar(velas, leitores_padrao(), HORIZONTES[0])
    alfa = P["alfa"] / P["n_testes"]
    dias = _dias(velas[base.inicio:])
    testes = []
    for h in HORIZONTES:
        prep = com_horizonte(base, h)
        for ag in AGREGADORES:
            sem_custo = rodar(prep, _config(h, ag, 0.0, 0.0), f"{ag} {h} min (sem custo)")
            real = rodar(prep, _config(h, ag, taxa_bps, SLIPPAGE_BPS), f"{ag} {h} min")
            brutos = [t["bruto"] for t in sem_custo.trades]
            bruto_medio = sum(brutos) / len(brutos) if brutos else 0.0
            h1, h2 = _metades(real)
            res = resumir(real)
            criterios = {"operações ≥ 200": res["operacoes"] >= P["min_operacoes"], f"p ≤ {alfa:.5f}": res["p_valor"] <= alfa,
                         "retorno > 0 (inteiro e nas duas metades)": res["retorno"] > 0 and h1 > 0 and h2 > 0}
            testes.append({
                "nome": f"{'agentes + logística' if ag == 'logistico' else 'agentes + média'} · {h} min", "horizonte": h, "agregador": ag,
                "ops_sem_custo": len(brutos), "ops_por_dia": len(brutos) / dias, "bruto_medio_bps": bruto_medio * 1e4,
                "equilibrio_bps_por_lado": bruto_medio * 1e4 / 2,
                "sensibilidade": {f"{c:g}": (bruto_medio * 1e4 - 2 * (c + SLIPPAGE_BPS if c else 0)) for c in CENARIOS_TAXA_BPS},
                "retorno": res["retorno"], "metade_1": h1, "metade_2": h2, "operacoes": res["operacoes"], "ops_por_dia_real": res["operacoes"] / dias,
                "p_valor": res["p_valor"], "ic95": res["ic95"], "desligado": real.desligado, "criterios": criterios, "passou": all(criterios.values())})
    aprovado = any(t["passou"] for t in testes)
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "protocolo": P, "taxa_bps": taxa_bps,
        "dados": {"velas": len(velas), "dias": round(dias, 1), "de": datetime.fromtimestamp(velas[0].t, timezone.utc).strftime("%Y-%m-%d"),
                  "ate": datetime.fromtimestamp(velas[-1].t, timezone.utc).strftime("%Y-%m-%d")},
        "buy_hold": velas[-1].c / velas[base.inicio].c - 1, "testes": testes, "aprovado": aprovado,
        "veredito": ("APROVADA para paper trading ao vivo (NÃO para dinheiro real): confirme com ≥ 8 semanas e ≥ 200 operações simuladas."
                     if aprovado else "REPROVADA: " + P["se_reprovar"] + "."),
    }


def formatar(v: dict) -> str:
    P, d = v["protocolo"], v["dados"]
    custo = v["taxa_bps"] + P["slippage_bps"]
    out = [P["hipotese"], f"dados: {d['velas']} velas de 1 min ({d['de']} → {d['ate']}, {d['dias']} dias) · custo {custo:g} bps por lado "
           f"(taxa {v['taxa_bps']:g} + derrapagem {P['slippage_bps']:g}) · comprar e segurar {v['buy_hold']:+.1%}",
           "critérios de aprovação (fixados antes de rodar): " + "; ".join(P["aprovacao"]),
           "\nPARTE 1 — o ganho BRUTO existe? (sem nenhum custo)",
           f"{'teste':<28}{'ops/dia':>9}{'bruto/op':>11}{'equilíbrio':>13}",
           ]
    for t in v["testes"]:
        out.append(f"{t['nome']:<28}{t['ops_por_dia']:>9.1f}{t['bruto_medio_bps']:>+9.2f}bp{t['equilibrio_bps_por_lado']:>+10.2f}bp/lado")
    out.append("   (equilíbrio = a maior taxa por lado com que ainda empata; negativo = perde mesmo sem custo)")
    out.append(f"\nPARTE 2 — com o seu custo real ({custo:g} bps por lado)")
    for t in v["testes"]:
        ic = t["ic95"]
        ic_txt = f"IC95% [{ic[0]:+.3%} , {ic[1]:+.3%}]" if ic[0] is not None else "poucas operações"
        out.append(f"{t['nome']:<28} retorno {t['retorno']:+.1%} (1ª {t['metade_1']:+.1%} · 2ª {t['metade_2']:+.1%}) · {t['operacoes']} ops "
                   f"({t['ops_por_dia_real']:.1f}/dia) · p={t['p_valor']:.4f} · {ic_txt}" + (f" · {t['desligado']}" if t["desligado"] else ""))
        out += [f"   {'✓' if ok else '✗'} {n}" for n, ok in t["criterios"].items()]
    out.append("\nVEREDITO: " + v["veredito"])
    return "\n".join(out)
