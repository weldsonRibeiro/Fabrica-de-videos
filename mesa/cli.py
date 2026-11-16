"""Linha de comando da mesa: `python -m mesa ...`"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from . import dados
from .backtest import Config, comparar
from .leitores import leitores_padrao
from .risco import ConfigRisco
from .sinal import avaliar, gerar_sinal, registrar

AVISO = ("⚠️  Simulação. Passado não garante futuro; backtest tende a ser otimista. Não é recomendação financeira "
         "e nada aqui envia ordens a corretoras.")


def _cfg(a) -> Config:
    return Config(horizonte=a.horizonte, taxa_bps=a.taxa, slippage_bps=a.slippage, capital=a.capital,
                  risco=ConfigRisco(permitir_short=a.short))


def _tabela(resultados) -> str:
    linhas = [f"{'estratégia':28}{'retorno':>9}{'buy&hold':>10}{'sharpe':>8}{'queda máx':>10}{'ops':>6}  {'IC95% por operação':24} veredito"]
    for r in resultados:
        ic = "—" if r.ic95[0] != r.ic95[0] else f"[{r.ic95[0]:+.2%} , {r.ic95[1]:+.2%}]"
        ver = "evidência de vantagem*" if r.significativo else ("poucas operações" if len(r.trades) < 30 else "sem evidência")
        if r.desligado:
            ver += " | " + r.desligado
        linhas.append(f"{r.nome:28}{r.retorno:>+9.1%}{r.buy_hold:>+10.1%}{r.sharpe:>8.2f}{r.max_dd:>10.1%}{len(r.trades):>6}  {ic:24} {ver}")
    return "\n".join(linhas)


def principal(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mesa", description="Mesa de operações: agentes + probabilidades + risco (simulação)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def comum(s):
        s.add_argument("--dados", required=True, help="CSV de velas (t,o,h,l,c,v)")
        s.add_argument("--horizonte", type=int, default=24, help="velas por operação (padrão 24)")
        s.add_argument("--taxa", type=float, default=10.0, help="corretagem por lado, em bps (padrão 10 = 0,10%%)")
        s.add_argument("--slippage", type=float, default=5.0, help="derrapagem por lado, em bps")
        s.add_argument("--capital", type=float, default=10000.0)
        s.add_argument("--short", action="store_true", help="permite vender a descoberto (derivativos)")
        s.add_argument("--de", help="usa só velas a partir de AAAA-MM-DD (para o teste final, em período nunca visto)")
        s.add_argument("--ate", help="usa só velas até AAAA-MM-DD (para ajustar sem espiar o período de teste)")

    s = sub.add_parser("sintetico", help="gera preços inventados para testar a estrutura")
    s.add_argument("--modo", choices=["ruido", "momentum", "regimes"], default="ruido")
    s.add_argument("--n", type=int, default=8760)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--saida", required=True)

    s = sub.add_parser("baixar", help="baixa histórico público da Binance (rode no SEU computador)")
    s.add_argument("--simbolo", default="BTCUSDT")
    s.add_argument("--intervalo", default="1h", choices=list(dados.INTERVALOS))
    s.add_argument("--desde", default="2021-01-01", help="AAAA-MM-DD")
    s.add_argument("--saida", required=True)

    s = sub.add_parser("backtest", help="testa a estratégia no passado, com custos, contra linhas de base")
    comum(s)
    s = sub.add_parser("sinal", help="recomendação SIMULADA para a última vela e registro no diário")
    comum(s)
    s.add_argument("--diario", required=True)
    s = sub.add_parser("avaliar", help="confere os sinais do diário contra o que o preço fez")
    comum(s)
    s.add_argument("--diario", required=True)

    s = sub.add_parser("vigiar", help="monitora o Bitcoin 24 h com dados reais e opera NA SIMULAÇÃO (nenhuma ordem real)")
    s.add_argument("--fonte", choices=["coinbase", "binance"], default="coinbase", help="coinbase funciona de IPs dos EUA; binance global não")
    s.add_argument("--simbolo", help="padrão: BTC-USD (coinbase) ou BTCUSDT (binance)")
    s.add_argument("--intervalo", default="1h")
    s.add_argument("--pasta", default="dados-mesa", help="onde guarda velas, diário, estado e eventos")
    s.add_argument("--checagem", type=float, default=60.0, help="segundos entre checagens de preço (stop/prazo)")
    s.add_argument("--uma-vez", action="store_true", help="roda um ciclo e sai (para teste ou cron)")
    s.add_argument("--servir", action="store_true", help="serve a página de status (protegida por FABRICA_PAINEL_CHAVE) e o /saude")
    s.add_argument("--host", default=os.environ.get("FABRICA_HOST", "127.0.0.1"))
    s.add_argument("--porta", type=int, default=int(os.environ.get("PORT", "8080")))
    s.add_argument("--horizonte", type=int, default=24)
    s.add_argument("--taxa", type=float, default=10.0)
    s.add_argument("--slippage", type=float, default=5.0)
    s.add_argument("--capital", type=float, default=10000.0)
    s.add_argument("--short", action="store_true")

    s = sub.add_parser("status", help="mostra o estado do vigia (posição simulada, resultado, último sinal)")
    s.add_argument("--pasta", default="dados-mesa")

    a = p.parse_args(argv)
    if a.cmd == "vigiar":
        from .fontes import FONTES
        from .vigia import Vigia

        simbolo = a.simbolo or ("BTC-USD" if a.fonte == "coinbase" else "BTCUSDT")
        fonte = FONTES[a.fonte](simbolo, a.intervalo)
        if a.servir:
            from .painel import servir_em_segundo_plano

            try:
                servir_em_segundo_plano(a.pasta, os.environ.get("FABRICA_PAINEL_CHAVE", ""), a.host, a.porta)
            except ValueError as erro:
                raise SystemExit(f"{erro}. Gere uma: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
            print(f"Página de status em http://{a.host}:{a.porta}/?k=<chave> (e /saude)", flush=True)
        v = Vigia(fonte, leitores_padrao(), _cfg(a), a.pasta)
        print(f"Vigiando {simbolo} ({a.fonte}, velas de {a.intervalo}) em SIMULAÇÃO. Estado em {a.pasta}/. Ctrl+C para parar.\n{AVISO}\n", flush=True)
        if a.uma_vez:
            for e in v.passo():
                print(e)
        else:
            try:
                v.rodar(a.checagem)
            except KeyboardInterrupt:
                print("parado.")
        return 0
    if a.cmd == "status":
        arq = Path(a.pasta) / "estado.json"
        if not arq.exists():
            raise SystemExit(f"sem estado em {a.pasta}/ (rode `vigiar` primeiro)")
        d = json.loads(arq.read_text(encoding="utf-8"))
        c, g = d["corretora"], d["guarda"]
        print(f"{d['modo']} · atualizado {d['atualizado_em']}")
        print(f"preço {d['preco']:,.2f} · capital {c['capital_inicial']:,.0f} → equity {d['equity']:,.2f} ({d['equity'] / c['capital_inicial'] - 1:+.2%})")
        pos = c["posicao"]
        print("posição: " + (f"{'COMPRADO' if pos['direcao'] > 0 else 'VENDIDO'} {pos['fracao']:.1%} do capital desde {datetime.fromtimestamp(pos['t_entrada'], timezone.utc):%d/%m %H:%M} UTC, stop {pos['stop']:,.2f}" if pos else "fora do mercado"))
        print(f"operações fechadas: {len(c['trades'])}" + (f" · último resultado {c['trades'][-1]['ret_capital']:+.2%} ({c['trades'][-1]['motivo']})" if c["trades"] else ""))
        print(f"risco: {'DESLIGADO — ' + g['motivo'] if g['desligado'] else 'ok'}")
        if d.get("ultimo_sinal"):
            u = d["ultimo_sinal"]
            print(f"último sinal: p(alta)={u['p']} · {u['motivo']}")
        print("\n" + AVISO)
        return 0
    if a.cmd == "sintetico":
        velas = dados.sintetico(a.n, a.seed, a.modo)
        dados.salvar_csv(velas, a.saida)
        print(f"{len(velas)} velas SINTÉTICAS (modo {a.modo}) em {a.saida}. Não são o mercado: servem para testar a estrutura.")
        return 0
    if a.cmd == "baixar":
        desde = int(datetime.fromisoformat(a.desde).replace(tzinfo=timezone.utc).timestamp())
        velas = dados.baixar_binance(a.simbolo, a.intervalo, desde)
        dados.validar(velas)
        dados.salvar_csv(velas, a.saida)
        print(f"{len(velas)} velas de {a.simbolo} ({a.intervalo}) em {a.saida}")
        return 0

    velas, cfg = dados.ler_csv(a.dados), _cfg(a)
    ts = lambda d: int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp())  # noqa: E731
    if a.de:
        velas = [v for v in velas if v.t >= ts(a.de)]
    if a.ate:
        velas = [v for v in velas if v.t < ts(a.ate) + 86400]
    if len(velas) < 700:
        raise SystemExit(f"poucas velas ({len(velas)}) depois do filtro de período; são necessárias ao menos ~700")
    if a.cmd == "backtest":
        res = comparar(velas, leitores_padrao(), cfg)
        print(f"{len(velas)} velas · horizonte {cfg.horizonte} · custo {cfg.taxa_bps + cfg.slippage_bps:.0f} bps por lado\n")
        print(_tabela(res))
        print("\n* IC 95% de retorno por operação acima de zero com ≥ 30 operações. É evidência, NÃO prova: confirme com dados que o")
        print("  modelo nunca viu (período novo) e em paper trading antes de qualquer dinheiro.")
        base = res[0].prob
        if base.get("n"):
            print(f"\nCalibração das probabilidades do agregador ({base['n']} previsões fora da amostra): "
                  f"Brier {base['brier']:.4f} (chutar 50% = 0,2500) · log-loss {base['logloss']:.4f} (50% = 0,6931) · acerto {base['acuracia']:.1%}")
            for b in base["tabela"]:
                print(f"  quando diz {b['faixa']:>8}: subiu {b['freq_real']:.0%} das vezes (média prevista {b['prob_media']:.0%}, n={b['n']})")
    elif a.cmd == "sinal":
        s = gerar_sinal(velas, leitores_padrao(), cfg)
        novo = registrar(Path(a.diario), s)
        print(f"vela {datetime.fromtimestamp(s['t'], timezone.utc):%Y-%m-%d %H:%M} UTC · preço {s['preco']:.2f}")
        for l in s["leituras"]:
            print(f"  {l['leitor']:24} p={l['p']:.2f} confiança {l['conf']:.2f}  {l['nota']}")
        print(f"\nprobabilidade agregada de alta: {s['p']}" if s["p"] is not None else "")
        print(f"decisão: {s['motivo']}" + (f" · {s['fracao']:.1%} do capital · stop {s['stop_pct']:.1%}" if s.get("direcao") else ""))
        print("(registrado no diário)" if novo else "(esta vela já estava no diário)")
    elif a.cmd == "avaliar":
        r = avaliar(Path(a.diario), velas, cfg)
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    print("\n" + AVISO)
    return 0
