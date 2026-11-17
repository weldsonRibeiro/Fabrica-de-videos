"""Varredura de horizontes: roda o mesmo backtest para vários horizontes e CORRIGE pelo número de testes feitos.

Testar muitas variações e ficar com a melhor quase sempre acha "vantagem" no acaso. Por isso:
- os horizontes são definidos ANTES de olhar os resultados;
- o limite de significância é dividido pelo nº de testes (correção de Bonferroni);
- um candidato precisa ser positivo também no período de teste (últimos meses).
Mesmo sobrevivendo, é só uma hipótese: a confirmação de verdade é o paper trading ao vivo, com dados que ainda não existiam.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .backtest import Config
from .dados import Vela
from .leitores import Leitor
from .relatorio import relatorio, tabela

HORIZONTES_PADRAO = [4, 8, 12, 24, 48, 96]
ALFA = 0.05


def varrer(velas: list[Vela], leitores: list[Leitor], cfg: Config | None = None, horizontes: list[int] | None = None,
          meses_teste: int = 12, avisos: list[str] | None = None, aoprogresso=None) -> dict:
    cfg = cfg or Config()
    horizontes = horizontes or HORIZONTES_PADRAO
    por_horizonte = []
    for h in horizontes:
        rel = relatorio(velas, leitores, replace(cfg, horizonte=h), meses_teste=meses_teste, avisos=avisos)
        cal = {k: rel["calibracao"].get(k) for k in ("n", "brier", "logloss", "acuracia")}
        por_horizonte.append({"horizonte": h, "completo": rel["completo"], "teste": rel["teste"], "calibracao": cal})
        if aoprogresso:
            aoprogresso(h)
    n_testes = len(horizontes) * len(por_horizonte[0]["completo"])
    alfa_corrigido = ALFA / n_testes
    nominais, candidatos = [], []
    for ph in por_horizonte:
        for r, t in zip(ph["completo"], ph["teste"]):
            base = {"horizonte": ph["horizonte"], "estrategia": r["nome"], "retorno": r["retorno"], "retorno_teste": t["retorno"],
                    "operacoes": r["operacoes"], "p_valor": r["p_valor"]}
            if r["retorno"] > 0 and r["operacoes"] >= 30 and r["p_valor"] <= ALFA:
                nominais.append(base)
                if r["p_valor"] <= alfa_corrigido and t["retorno"] > 0:
                    candidatos.append(base)
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "horizontes": horizontes, "meses_teste": meses_teste,
        "config": {"taxa_bps": cfg.taxa_bps, "slippage_bps": cfg.slippage_bps, "leitores": [l.nome for l in leitores],
                   "velas": len(velas), "de": datetime.fromtimestamp(velas[0].t, timezone.utc).strftime("%Y-%m-%d"),
                   "ate": datetime.fromtimestamp(velas[-1].t, timezone.utc).strftime("%Y-%m-%d")},
        "n_testes": n_testes, "alfa": ALFA, "alfa_corrigido": alfa_corrigido,
        "esperados_por_sorte": round(n_testes * ALFA, 1), "nominais": nominais, "candidatos": candidatos,
        "por_horizonte": por_horizonte, "veredito": veredito(n_testes, alfa_corrigido, nominais, candidatos), "avisos": avisos or [],
    }


def veredito(n_testes: int, alfa_corrigido: float, nominais: list, candidatos: list) -> list[str]:
    linhas = [f"Foram feitos {n_testes} testes (horizontes × estratégias). Só por sorte, com 95% de confiança, esperaria-se cerca de "
              f"{n_testes * ALFA:.1f} resultados 'positivos'; apareceram {len(nominais)}."]
    if candidatos:
        nomes = ", ".join(f"{c['estrategia']} @ {c['horizonte']}h" for c in candidatos)
        linhas.append(f"Sobrevivem à correção pelo nº de testes (p ≤ {alfa_corrigido:.4f}) e são positivos também no teste: {nomes}. "
                      "É uma HIPÓTESE, não uma vantagem comprovada: confirme em paper trading ao vivo antes de qualquer dinheiro.")
    else:
        linhas.append(f"NENHUM sobrevive à correção pelo número de testes (p ≤ {alfa_corrigido:.4f}) com retorno positivo também no teste. "
                      "Não há evidência de vantagem em nenhum horizonte testado.")
    linhas.append("O período de teste (últimos meses) já havia sido visto com horizonte de 24 h: trate esta varredura como EXPLORAÇÃO. "
                  "A confirmação limpa só vem de dados que ainda não existiam (paper trading ao vivo).")
    return linhas


def formatar(v: dict) -> str:
    c = v["config"]
    out = [f"VARREDURA DE HORIZONTES · {c['velas']} velas ({c['de']} → {c['ate']}) · custo {c['taxa_bps'] + c['slippage_bps']:.0f} bps por lado · "
           f"leitores: {', '.join(c['leitores'])}"]
    for ph in v["por_horizonte"]:
        cal = ph["calibracao"]
        out.append(f"\n== horizonte {ph['horizonte']} h · Brier {cal['brier']:.4f} (50% = 0,2500) · acerto {cal['acuracia']:.1%} ==\n"
                   + tabela(ph["completo"][:2] + [x for x in ph["completo"][2:] if x["significativo"]])
                   + f"\n   teste {v['meses_teste']} meses: " + " · ".join(f"{t['nome']} {t['retorno']:+.1%} ({t['operacoes']} ops)" for t in ph["teste"][:2]))
    out.append("\nVEREDITO:")
    out += ["  • " + l for l in v["veredito"]]
    return "\n".join(out)
