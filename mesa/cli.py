"""Linha de comando da mesa: `python -m mesa ...`"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from . import dados
from .backtest import Config
from . import leitores
from .leitores import leitores_padrao
from .risco import ConfigRisco
from .relatorio import formatar, relatorio
from .sinal import avaliar, gerar_sinal, registrar

AVISO = ("⚠️  Simulação. Passado não garante futuro; backtest tende a ser otimista. Não é recomendação financeira "
         "e nada aqui envia ordens a corretoras.")


def _cfg(a) -> Config:
    return Config(horizonte=a.horizonte, taxa_bps=a.taxa, slippage_bps=a.slippage, capital=a.capital,
                  risco=ConfigRisco(permitir_short=a.short))


def montar_leitores(args, velas=None, com_atualizadores: bool = False):
    """Leitores padrão + os extras pedidos (baixam dados de fora). Falha de rede vira aviso, não derruba nada.
    Com `velas=None` (modo ao vivo) baixa só os últimos ~120 dias de funding."""
    import time

    from . import externos

    extras, avisos, atualizadores = [], [], []
    agora = int(time.time())
    if getattr(args, "medo", False):
        try:
            serie = externos.baixar_medo()
            extras.append(leitores.MedoGanancia(serie))
            atualizadores.append(lambda s=serie: s.adicionar(externos.baixar_medo().pontos()))
        except Exception as e:  # noqa: BLE001
            avisos.append(f"índice de medo e ganância indisponível ({e})")
    if getattr(args, "funding", None):
        try:
            desde = (velas[0].t if velas else agora - 120 * 86400) - 30 * 86400
            serie = externos.FUNDING[args.funding](desde=desde, ate=velas[-1].t if velas else None)
            if not len(serie):
                raise ValueError("a API não devolveu dados")
            extras.append(leitores.Funding(serie))
            atualizadores.append(lambda s=serie, f=args.funding: s.adicionar(externos.FUNDING[f](desde=int(time.time()) - 5 * 86400).pontos()))
        except Exception as e:  # noqa: BLE001
            avisos.append(f"funding ({args.funding}) indisponível ({e}); algumas redes/países bloqueiam essa API")
    lista = leitores_padrao(extras)
    return (lista, avisos, atualizadores) if com_atualizadores else (lista, avisos)


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
        s.add_argument("--medo", action="store_true", help="inclui o leitor de medo e ganância (baixa o índice; sem chave)")
        s.add_argument("--funding", choices=["binance", "bybit"], help="inclui o leitor de funding de perpétuos (algumas redes bloqueiam)")

    s = sub.add_parser("sintetico", help="gera preços inventados para testar a estrutura")
    s.add_argument("--modo", choices=["ruido", "momentum", "regimes"], default="ruido")
    s.add_argument("--n", type=int, default=8760)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--saida", required=True)

    s = sub.add_parser("baixar", help="baixa histórico público de preços (sem chave)")
    s.add_argument("--fonte", choices=["coinbase", "binance"], default="coinbase", help="coinbase: BTC-USD, funciona de quase qualquer lugar; binance: BTCUSDT")
    s.add_argument("--simbolo", help="padrão: BTC-USD (coinbase) ou BTCUSDT (binance)")
    s.add_argument("--intervalo", default="1h", choices=list(dados.INTERVALOS))
    s.add_argument("--desde", default="2023-01-01", help="AAAA-MM-DD")
    s.add_argument("--ate", help="AAAA-MM-DD (padrão: agora)")
    s.add_argument("--saida", required=True)

    s = sub.add_parser("backtest", help="testa a estratégia no passado, com custos, contra linhas de base")
    comum(s)
    s.add_argument("--meses-teste", type=int, default=12, help="últimos N meses tratados como teste (padrão 12)")
    s.add_argument("--json", help="salva o relatório completo neste arquivo")
    s = sub.add_parser("varrer", help="roda o backtest em vários horizontes e CORRIGE pelo nº de testes (evita achar vantagem por sorte)")
    comum(s)
    s.add_argument("--horizontes", default="4,8,12,24,48,96", help="lista em horas, separada por vírgula (defina ANTES de olhar os resultados)")
    s.add_argument("--meses-teste", type=int, default=12)
    s.add_argument("--json", help="salva o resultado completo neste arquivo")
    s = sub.add_parser("hipotese", help="roda uma hipótese PRÉ-REGISTRADA (parâmetros e critérios fixos no código)")
    s.add_argument("nome", choices=["funding"], help="funding = H1: o funding dos perpétuos informa o retorno das próximas 24 h")
    s.add_argument("--dados", required=True, help="CSV de velas de 1 h")
    s.add_argument("--funding", choices=["binance", "bybit"], required=True, help="de onde baixar o histórico de funding")
    s.add_argument("--json", help="salva o resultado neste arquivo")
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
    s.add_argument("--medo", action="store_true", default=os.environ.get("MESA_MEDO", "1") == "1", help="leitor de medo e ganância (padrão ligado; MESA_MEDO=0 desliga)")
    s.add_argument("--funding", choices=["binance", "bybit"], default=os.environ.get("MESA_FUNDING") or None, help="leitor de funding (env MESA_FUNDING)")
    s.add_argument("--backtest-dias", type=int, default=int(os.environ.get("MESA_BACKTEST_DIAS", "730")),
                   help="roda sozinho um backtest com N dias de histórico real e refaz toda semana (0 desliga; padrão 730)")
    s.add_argument("--servir", action="store_true", help="serve a página de status (protegida por FABRICA_PAINEL_CHAVE) e o /saude")
    s.add_argument("--host", default=os.environ.get("FABRICA_HOST", "127.0.0.1"))
    s.add_argument("--porta", type=int, default=int(os.environ.get("PORT", "8080")))
    s.add_argument("--horizonte", type=int, default=24)
    s.add_argument("--taxa", type=float, default=10.0)
    s.add_argument("--slippage", type=float, default=5.0)
    s.add_argument("--capital", type=float, default=10000.0)
    s.add_argument("--short", action="store_true")

    s = sub.add_parser("coletar", help="coleta 24 h dados de curto prazo (velas de 1 min + melhor compra/venda e spread) no SEU computador")
    s.add_argument("--fonte", choices=["coinbase", "binance"], default="binance")
    s.add_argument("--simbolo", help="padrão: BTC-USD (coinbase) ou BTCUSDT (binance)")
    s.add_argument("--pasta", default="dados-mesa", help="pasta de dados (a mesma do painel)")
    s.add_argument("--livro-cada", type=float, default=10.0, help="segundos entre fotos do melhor preço de compra/venda (padrão 10)")
    s.add_argument("--uma-vez", action="store_true", help="coleta um ciclo e sai")
    s.add_argument("--resumo", action="store_true", help="só mostra o que já foi coletado (spread médio, dias, velas) e sai")
    s = sub.add_parser("curto", help="H2 (curto prazo, PRÉ-REGISTRADA): mede o ganho bruto por operação e o custo de equilíbrio com velas de 1 min")
    s.add_argument("--dados", required=True, help="CSV de velas de 1 min (baixe com: baixar --intervalo 1m)")
    s.add_argument("--taxa-bps", type=float, default=10.0, help="SUA taxa por lado em bps (Binance spot: 10 padrão, 7,5 com BNB). É um fato da conta, fica registrada")
    s.add_argument("--json", help="salva o resultado também neste arquivo")
    s.add_argument("--pasta", default="dados-mesa", help="grava o resultado em PASTA/curto.json, de onde o painel lê")
    s = sub.add_parser("painel", help="abre o painel no navegador, no seu computador (resultado do H2, coletor, backtest, vigia)")
    s.add_argument("--pasta", default="dados-mesa")
    s.add_argument("--porta", type=int, default=8080)
    s.add_argument("--curto", help="resultado do H2 já salvo (ex.: h2.json) para mostrar no painel")
    s.add_argument("--celular", action="store_true", help="deixa abrir no celular, na MESMA rede Wi-Fi (continua exigindo a chave; não fica na internet)")

    s = sub.add_parser("status", help="mostra o estado do vigia (posição simulada, resultado, último sinal)")
    s.add_argument("--pasta", default="dados-mesa")

    a = p.parse_args(argv)
    if a.cmd == "coletar":
        from . import coletor
        from .fontes import FONTES

        if a.resumo:
            r = coletor.resumo(a.pasta)
            if "livro" not in r and "velas" not in r:
                raise SystemExit(f"nada coletado em {a.pasta}/ ainda (rode `coletar` primeiro)")
            if "livro" in r:
                l = r["livro"]
                print(f"livro de ofertas: {l['fotos']} fotos em {l['dias']} dia(s) · spread médio {l['spread_bps_medio']:.3f} bps · mediana {l['spread_bps_mediana']:.3f} · "
                      f"p95 {l['spread_bps_p95']:.3f} · máximo {l['spread_bps_max']:.3f}  (cruzar o spread custa metade disso por lado)")
            if "velas" in r:
                v = r["velas"]
                print(f"velas de 1 min: {v['n']} ({v['dias']} dia(s)) de {v['de']} a {v['ate']} UTC")
            return 0
        simbolo = a.simbolo or ("BTC-USD" if a.fonte == "coinbase" else "BTCUSDT")
        c = coletor.Coletor(FONTES[a.fonte](simbolo, "1m"), a.pasta)
        print(f"Coletando {simbolo} ({a.fonte}): velas de 1 min + melhor compra/venda a cada {a.livro_cada:g} s em {a.pasta}/. Só leitura de dados públicos. Ctrl+C para parar.", flush=True)
        try:
            if a.uma_vez:
                print(c.passo())
            else:
                c.rodar(a.livro_cada)
        except KeyboardInterrupt:
            print("parado. (resumo: python -m mesa coletar --resumo)")
        return 0
    if a.cmd == "painel":
        import secrets
        import shutil
        import webbrowser

        from .painel import servidor

        pasta = Path(a.pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        if a.curto:
            shutil.copyfile(a.curto, pasta / "curto.json")
        arq_chave = pasta / "painel.chave"
        chave = os.environ.get("FABRICA_PAINEL_CHAVE") or (arq_chave.read_text(encoding="utf-8").strip() if arq_chave.exists() else "")
        if len(chave) < 16:
            chave = secrets.token_urlsafe(24)
            arq_chave.write_text(chave, encoding="utf-8")
        try:
            srv = servidor(pasta, chave, "0.0.0.0" if a.celular else "127.0.0.1", a.porta)
        except OSError as e:
            raise SystemExit(f"não consegui abrir a porta {a.porta} ({e}). Tente outra: --porta 8081")
        url = f"http://127.0.0.1:{a.porta}/?k={chave}"
        if a.celular:
            import socket

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
                    sk.connect(("192.0.2.1", 9))      # só descobre a rede; não envia nada
                    ip = sk.getsockname()[0]
            except OSError:
                ip = "IP-DO-SEU-COMPUTADOR"
            print(f"No CELULAR (mesma rede Wi-Fi): http://{ip}:{a.porta}/?k={chave}\n"
                  "Se o Windows perguntar sobre o firewall, permita só em 'Rede privada'.", flush=True)
        print(f"No computador: {url}\n(Ctrl+C para fechar)", flush=True)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("painel fechado.")
        return 0
    if a.cmd == "curto":
        from .curto import PROTOCOLO_H2, avaliar_curto, formatar as formatar_curto

        velas = dados.ler_csv(a.dados)
        if len(velas) < 2 or velas[1].t - velas[0].t != 60:
            raise SystemExit("esta hipótese usa velas de 1 minuto: baixe com `baixar --fonte binance --intervalo 1m --desde AAAA-MM-DD --saida ...`")
        print(f"Protocolo fixo: horizontes {PROTOCOLO_H2['horizontes_min']} min, {PROTOCOLO_H2['n_testes']} testes, custo {a.taxa_bps:g}+{PROTOCOLO_H2['slippage_bps']:g} bps por lado. "
              "Se reprovar, a hipótese está encerrada.\nCalculando as leituras (alguns minutos)…", flush=True)
        try:
            v = avaliar_curto(velas, a.taxa_bps)
        except ValueError as e:
            raise SystemExit(str(e))
        print("\n" + formatar_curto(v))
        Path(a.pasta).mkdir(parents=True, exist_ok=True)
        (Path(a.pasta) / "curto.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nresultado no painel: python -m mesa painel --pasta {a.pasta}")
        if a.json:
            Path(a.json).write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nresultado completo em {a.json}")
        print("\n" + AVISO)
        return 0
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
        lista, avisos, atualizadores = montar_leitores(a, None, com_atualizadores=True)
        for aviso in avisos:
            print(f"aviso: {aviso}", flush=True)
        v = Vigia(fonte, lista, _cfg(a), a.pasta, atualizadores=atualizadores)
        if a.backtest_dias > 0 and not a.uma_vez:
            from .servico import iniciar_em_segundo_plano

            iniciar_em_segundo_plano(a.pasta, a.fonte, simbolo, a.intervalo, a.backtest_dias, _cfg(a),
                                     lambda velas: montar_leitores(a, velas))
            print(f"Backtest automático em segundo plano ({a.backtest_dias} dias de histórico real; refaz toda semana).", flush=True)
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
        ate = int(datetime.fromisoformat(a.ate).replace(tzinfo=timezone.utc).timestamp()) + 86400 if a.ate else None
        simbolo = a.simbolo or ("BTC-USD" if a.fonte == "coinbase" else "BTCUSDT")
        try:
            if a.fonte == "coinbase":
                velas = dados.baixar_coinbase(simbolo, a.intervalo, desde, ate, progresso=lambda n: print(f"\r{n} velas…", end="", flush=True))
                print()
            else:
                velas = dados.baixar_binance(simbolo, a.intervalo, desde, ate)
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"não consegui baixar ({e}). Se a sua rede bloqueia essa fonte, tente --fonte {'binance' if a.fonte == 'coinbase' else 'coinbase'}.")
        dados.validar(velas)
        dados.salvar_csv(velas, a.saida)
        print(f"{len(velas)} velas de {simbolo} ({a.intervalo}, {a.fonte}) em {a.saida} · velas faltando no meio: {dados.contar_lacunas(velas)}")
        return 0

    if a.cmd == "hipotese":
        from . import externos
        from .hipotese import PROTOCOLO_H1, avaliar_funding, formatar as formatar_hipotese

        velas = dados.ler_csv(a.dados)
        if velas[1].t - velas[0].t != 3600:
            raise SystemExit("esta hipótese usa velas de 1 hora")
        if len(velas) < 8000:
            raise SystemExit(f"são necessárias ao menos ~8.000 velas de 1 h (≈ 11 meses); o arquivo tem {len(velas)}. Baixe mais histórico.")
        print(f"Protocolo fixo: horizonte {PROTOCOLO_H1['horizonte']} h, custo {PROTOCOLO_H1['taxa_bps'] + PROTOCOLO_H1['slippage_bps']:.0f} bps por lado, {PROTOCOLO_H1['n_testes']} testes. "
              "Não há parâmetros para mexer: se reprovar, a hipótese está encerrada.\nBaixando o funding…", flush=True)
        try:
            serie = externos.FUNDING[a.funding](desde=velas[0].t - 30 * 86400, ate=velas[-1].t)
            if not len(serie):
                raise ValueError("a API não devolveu dados")
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"não consegui baixar o funding de {a.funding} ({e}). Tente a outra fonte (--funding binance|bybit) ou outra rede.")
        v = avaliar_funding(velas, serie)
        print("\n" + formatar_hipotese(v))
        if a.json:
            Path(a.json).write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nresultado completo em {a.json}")
        print("\n" + AVISO)
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
        lista, avisos = montar_leitores(a, velas)
        rel = relatorio(velas, lista, cfg, meses_teste=a.meses_teste, fonte=a.dados, avisos=avisos)
        print(formatar(rel))
        if a.json:
            Path(a.json).write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nrelatório completo em {a.json}")
    elif a.cmd == "varrer":
        from .varredura import formatar as formatar_varredura, varrer

        lista, avisos = montar_leitores(a, velas)
        hs = [int(x) for x in a.horizontes.split(",") if x.strip()]
        v = varrer(velas, lista, cfg, hs, meses_teste=a.meses_teste, avisos=avisos, aoprogresso=lambda h: print(f"  horizonte {h} h pronto", flush=True))
        print("\n" + formatar_varredura(v))
        for av in avisos:
            print("  ! " + av)
        if a.json:
            Path(a.json).write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nresultado completo em {a.json}")
    elif a.cmd == "sinal":
        lista, _ = montar_leitores(a, velas)
        s = gerar_sinal(velas, lista, cfg)
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
