import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from mesa import backtest, dados
from mesa.agregador import RegLog, metricas
from mesa.backtest import Config, preparar, rodar
from mesa.cli import principal
from mesa.dados import Vela
from mesa.leitores import Noticias, Regime, leitores_padrao
from mesa.risco import ConfigRisco, GuardaRisco, avaliar_entrada
from mesa.sinal import avaliar, gerar_sinal, registrar


def vela(t, o, h, l, c, v=100.0):
    return Vela(t, o, h, l, c, v)


class TestSemOlharOFuturo(unittest.TestCase):
    def test_leituras_nao_mudam_quando_o_futuro_muda(self):
        velas = dados.sintetico(600, seed=11, modo="regimes")
        corte = 400
        alterado = velas[: corte + 1] + [vela(v.t, v.o * 3, v.h * 3, v.l * 3, v.c * 3, v.v * 9) for v in velas[corte + 1:]]
        a, b = preparar(velas, leitores_padrao(), 12), preparar(alterado, leitores_padrao(), 12)
        for i in range(a.inicio, corte + 1):
            self.assertEqual(a.X[i], b.X[i], f"a leitura de {i} dependeu do futuro")
            self.assertEqual(a.vol[i], b.vol[i])

    def test_noticias_so_usam_o_que_ja_era_publico(self):
        velas = dados.sintetico(10, seed=1)
        t = velas[-1].t
        n = Noticias(lambda agora: [(t - 3600, 1.0), (t + 3600, -1.0)])          # a segunda é do futuro
        self.assertGreater(n.ler(velas).p, 0.5)
        self.assertEqual(Noticias().ler(velas).conf, 0.0)                        # sem fonte, sem opinião

    def test_leitor_de_regime_veta_volatilidade_explosiva(self):
        calmo = [vela(i * 3600, 100 + (i % 2) * 0.1, 100.3, 99.9, 100 + ((i + 1) % 2) * 0.1) for i in range(130)]
        self.assertFalse(Regime().ler(calmo).veto)
        explosivo = calmo[:-8] + [vela((122 + i) * 3600, 100, 106, 94, 100 + (5 if i % 2 else -5)) for i in range(8)]
        self.assertTrue(Regime().ler(explosivo).veto)


class TestProbabilidades(unittest.TestCase):
    def test_brier_e_calibracao(self):
        self.assertAlmostEqual(metricas([1.0, 0.0, 1.0], [1, 0, 1])["brier"], 0.0)
        self.assertAlmostEqual(metricas([0.5] * 4, [1, 0, 1, 0])["brier"], 0.25)
        m = metricas([0.9] * 10 + [0.1] * 10, [1] * 9 + [0] + [0] * 9 + [1])
        self.assertAlmostEqual(m["tabela"][-1]["freq_real"], 0.9)

    def test_regressao_logistica_aprende_a_relacao(self):
        import random

        rnd = random.Random(0)
        X = [[rnd.gauss(0, 1), rnd.gauss(0, 1)] for _ in range(1500)]
        y = [int(rnd.random() < 1 / (1 + 2.718 ** (-(2 * a - 0 * b)))) for a, b in X]
        m = RegLog()
        m.ajustar(X, y)
        self.assertGreater(m.prob([2.0, 0.0]), 0.8)
        self.assertLess(m.prob([-2.0, 0.0]), 0.2)
        self.assertAlmostEqual(m.prob([0.0, 3.0]), m.prob([0.0, -3.0]), delta=0.12)   # o 2º fator é irrelevante


class TestRisco(unittest.TestCase):
    def test_nao_opera_sem_vantagem_nem_quando_custos_comem_o_valor_esperado(self):
        cfg = ConfigRisco()
        self.assertEqual(avaliar_entrada(0.51, 0.005, 24, 10, 5, cfg).direcao, 0)           # perto de 50%
        self.assertEqual(avaliar_entrada(0.40, 0.005, 24, 10, 5, cfg).direcao, 0)           # queda: spot não vende
        d = avaliar_entrada(0.56, 0.005, 24, 10, 5, cfg)
        self.assertEqual(d.direcao, 0)
        self.assertIn("custos", d.motivo)
        self.assertEqual(avaliar_entrada(0.40, 0.005, 24, 1, 0, replace(cfg, permitir_short=True)).direcao, -1)

    def test_tamanho_respeita_os_tetos(self):
        cfg = ConfigRisco()
        d = avaliar_entrada(0.99, 0.02, 24, 1, 0, cfg)
        self.assertEqual(d.direcao, 1)
        self.assertLessEqual(d.fracao, cfg.max_posicao)
        self.assertLessEqual(d.fracao * d.stop_pct, cfg.risco_por_operacao + 1e-12)          # no stop perde ≤ 1% do capital

    def test_limite_do_dia_e_kill_switch(self):
        g = GuardaRisco(ConfigRisco(perda_max_dia=0.03, drawdown_max=0.20), 1000)
        g.atualizar(0, 1000)
        self.assertTrue(g.pode_operar(1000)[0])
        g.atualizar(3600, 960)
        self.assertEqual(g.pode_operar(960), (False, "limite de perda do dia atingido"))
        g.atualizar(86400 + 10, 960)                                                          # dia novo: liberado
        self.assertTrue(g.pode_operar(960)[0])
        g.atualizar(86400 * 2, 790)                                                           # -21% do topo
        self.assertTrue(g.desligado)
        g.atualizar(86400 * 3, 1500)
        self.assertFalse(g.pode_operar(1500)[0])                                              # desligado não volta sozinho


class TestBacktest(unittest.TestCase):
    def momentum(self, seed=2):
        return dados.sintetico(8000, seed=seed, modo="momentum")

    def test_custos_reduzem_o_resultado(self):
        prep = preparar(self.momentum(), leitores_padrao(), 6)
        barato = rodar(prep, Config(horizonte=6, taxa_bps=1, slippage_bps=0))
        caro = rodar(prep, Config(horizonte=6, taxa_bps=30, slippage_bps=10))
        self.assertGreater(barato.retorno, caro.retorno)

    def test_nao_inventa_vantagem_no_ruido(self):
        for seed in (1, 2, 3):
            prep = preparar(dados.sintetico(8000, seed=seed, modo="ruido"), leitores_padrao(), 6)
            for taxa in (1, 15):
                r = rodar(prep, Config(horizonte=6, taxa_bps=taxa, slippage_bps=0))
                self.assertFalse(r.significativo, f"achou 'vantagem' em puro ruído (seed {seed}, custo {taxa})")

    def test_detecta_vantagem_real_quando_ela_existe_e_o_custo_permite(self):
        for seed in (1, 2, 3):
            prep = preparar(self.momentum(seed), leitores_padrao(), 6)
            r = rodar(prep, Config(horizonte=6, taxa_bps=1, slippage_bps=0))
            self.assertGreater(r.retorno, 0, seed)
            self.assertTrue(r.significativo, seed)

    def test_vantagem_pequena_nao_sobrevive_a_custos_realistas(self):
        prep = preparar(self.momentum(), leitores_padrao(), 6)
        self.assertFalse(rodar(prep, Config(horizonte=6, taxa_bps=10, slippage_bps=5)).significativo)

    def test_kill_switch_desliga_e_para_de_operar(self):
        prep = preparar(self.momentum(), leitores_padrao(), 6)
        r = rodar(prep, Config(horizonte=6, taxa_bps=1, slippage_bps=0, risco=ConfigRisco(drawdown_max=0.0005)))
        self.assertIn("KILL SWITCH", r.desligado)
        ultimo = max(t["t_entrada"] for t in r.trades) if r.trades else 0
        self.assertLess(len(r.trades), 20)
        self.assertGreaterEqual(prep.velas[-1].t, ultimo)

    def test_stop_limita_a_perda_e_executa_na_abertura_seguinte(self):
        velas = [vela(i * 3600, 100.0, 100.05, 99.95, 100.0) for i in range(230)]
        velas += [vela(230 * 3600, 100.0, 100.0, 90.0, 91.0)] + [vela((231 + i) * 3600, 91, 91.05, 90.95, 91) for i in range(30)]

        class Sempre:
            def __init__(self, colunas=None): ...
            def pronto(self): return True
            def prob(self, x): return 0.95

        with mock.patch.object(backtest, "AgregadorMedia", Sempre):
            r = rodar(preparar(velas, leitores_padrao(), 12), Config(horizonte=12, agregador="media", taxa_bps=0, slippage_bps=0))
        com_stop = [t for t in r.trades if t["parou_no_stop"]]
        self.assertTrue(com_stop, "o gap de -10% deveria ter ativado o stop")
        self.assertLess(com_stop[0]["ret_capital"], 0)
        self.assertGreater(com_stop[0]["ret_capital"], -0.5 * 0.1 - 1e-9)                 # perda limitada pelo tamanho da posição


class TestDadosEDiario(unittest.TestCase):
    def test_csv_ida_e_volta_e_validacao(self):
        velas = dados.sintetico(50, seed=1)
        with tempfile.TemporaryDirectory() as tmp:
            dados.salvar_csv(velas, Path(tmp) / "a.csv")
            self.assertEqual(dados.ler_csv(Path(tmp) / "a.csv"), velas)
        with self.assertRaises(ValueError):
            dados.validar([vela(0, 1, 1, 1, 1), vela(0, 1, 1, 1, 1)])                    # tempo repetido
        with self.assertRaises(ValueError):
            dados.validar([vela(0, 100, 99, 98, 100)])                                    # máxima menor que a abertura

    def test_baixar_binance_pagina_e_para_no_fim(self):
        chamadas = []

        def transporte(url):
            chamadas.append(url)
            inicio = int(url.split("startTime=")[1]) // 1000
            n = 1000 if len(chamadas) == 1 else 300
            return json.dumps([[(inicio + i * 3600) * 1000, "1", "2", "0.5", "1.5", "10", 0] for i in range(n)]).encode()

        velas = dados.baixar_binance("BTCUSDT", "1h", 1_600_000_000, transporte=transporte)
        self.assertEqual((len(velas), len(chamadas)), (1300, 2))
        self.assertEqual(velas[1000].t, velas[999].t + 3600)

    def test_diario_e_avaliacao(self):
        velas = dados.sintetico(900, seed=5, modo="momentum")
        cfg = Config(horizonte=6, taxa_bps=1, slippage_bps=0)
        with tempfile.TemporaryDirectory() as tmp:
            diario = Path(tmp) / "d.jsonl"
            s = gerar_sinal(velas[:800], leitores_padrao(), cfg)
            self.assertTrue(registrar(diario, s))
            self.assertFalse(registrar(diario, s))                                         # idempotente por vela
            self.assertEqual(len(diario.read_text().splitlines()), 1)
            diario.write_text(json.dumps({"t": velas[700].t, "horizonte": 6, "direcao": 1, "fracao": 0.2}) + "\n")
            r = avaliar(diario, velas, cfg)
            esperado = (velas[706].c / velas[701].o - 1) * 1 * 0.2
            self.assertAlmostEqual(r["retorno_medio_por_operacao"], esperado - 2 * 1e-4 * 0.2, places=9)   # custo de ida e volta sobre a fração

    def test_sinal_sem_dados_suficientes_nao_chuta(self):
        s = gerar_sinal(dados.sintetico(300, seed=1), leitores_padrao(), Config())
        self.assertEqual((s["p"], s["direcao"]), (None, 0))
        self.assertIn("insuficientes", s["motivo"])

    def test_cli_ponta_a_ponta(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            csv = str(Path(tmp) / "x.csv")
            self.assertEqual(principal(["sintetico", "--modo", "ruido", "--n", "1500", "--saida", csv]), 0)
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                self.assertEqual(principal(["backtest", "--dados", csv, "--horizonte", "6"]), 0)
            texto = saida.getvalue()
            self.assertIn("agentes + logístico", texto)
            self.assertIn("Não é recomendação financeira", texto)


if __name__ == "__main__":
    unittest.main()


class TestPeriodos(unittest.TestCase):
    def test_filtro_de_periodo_separa_ajuste_e_teste(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            csv = str(Path(tmp) / "x.csv")
            principal(["sintetico", "--modo", "ruido", "--n", "3000", "--seed", "3", "--saida", csv])     # ~125 dias a partir de 2020-09-13
            for args, esperado in ((["--ate", "2020-11-30"], "velas"), (["--de", "2020-11-01"], "velas")):
                saida = io.StringIO()
                with contextlib.redirect_stdout(saida):
                    self.assertEqual(principal(["backtest", "--dados", csv, "--horizonte", "6"] + args), 0)
                self.assertIn(esperado, saida.getvalue())
            with self.assertRaises(SystemExit):
                principal(["backtest", "--dados", csv, "--de", "2021-01-01"])                         # nada sobra: recusa


class FonteFalsa:
    """Revela as velas aos poucos, como o relógio andando; o preço é o fechamento da última vela revelada."""

    passo = 3600

    def __init__(self, velas):
        self.todas, self.agora = velas, velas[0].t
        self.chamadas = 0

    def avancar(self, n=1):
        self.agora = self.todas[min(len(self.todas) - 1, self.indice() + n)].t + self.passo

    def indice(self):
        return max(i for i, v in enumerate(self.todas) if v.t + self.passo <= self.agora)

    def velas(self, n, agora=None):
        self.chamadas += 1
        return [v for v in self.todas if v.t + self.passo <= self.agora][-n:]

    def preco(self):
        return self.todas[self.indice()].c


class TestVigia(unittest.TestCase):
    def montar(self, tmp, velas=None, **cfg):
        from mesa.vigia import Vigia

        velas = velas or dados.sintetico(1400, seed=2, modo="momentum")
        fonte = FonteFalsa(velas)
        fonte.agora = velas[899].t + 3600
        c = Config(horizonte=6, agregador="media", taxa_bps=1, slippage_bps=0, **cfg)
        return Vigia(fonte, leitores_padrao(), c, tmp), fonte

    def test_a_cada_vela_nova_grava_sinal_e_nao_repete(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, fonte = self.montar(tmp)
            v.passo(fonte.agora)
            v.passo(fonte.agora)                                                   # mesma vela: não pensa de novo
            self.assertEqual(len((Path(tmp) / "diario.jsonl").read_text().splitlines()), 1)
            fonte.avancar()
            v.passo(fonte.agora)
            self.assertEqual(len((Path(tmp) / "diario.jsonl").read_text().splitlines()), 2)

    def test_opera_so_na_simulacao_e_fecha_por_prazo_ou_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, fonte = self.montar(tmp)
            for _ in range(250):
                fonte.avancar()
                v.passo(fonte.agora)
            fechados = v.corretora.trades
            self.assertGreater(len(fechados), 3, "com momentum e custo baixo deveria operar algumas vezes")
            self.assertTrue({t["motivo"] for t in fechados} <= {"prazo", "stop"})
            self.assertEqual(json.loads((Path(tmp) / "estado.json").read_text())["modo"], "SIMULAÇÃO (nenhuma ordem real é enviada)")

    def test_stop_fecha_no_preco_observado(self):
        from mesa.corretora import CorretoraSimulada

        c = CorretoraSimulada(1000, 0, 0)
        self.assertTrue(c.abrir(0, 100.0, 1, 0.5, 0.02, 0.6, 10_000))
        self.assertIsNone(c.marcar(60, 99.0))                                       # ainda acima do stop (98)
        t = c.marcar(120, 97.0)                                                     # furou: sai no preço visto (pior que o stop)
        self.assertEqual(t["motivo"], "stop")
        self.assertAlmostEqual(c.caixa, 1000 + 500 * (97 / 100 - 1), places=6)
        self.assertFalse(c.abrir(130, 100, 1, 0, 0.02, 0.6, 1))                     # fração zero: não abre

    def test_reiniciar_continua_de_onde_parou(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, fonte = self.montar(tmp)
            for _ in range(120):
                fonte.avancar()
                v.passo(fonte.agora)
            antes = (v.corretora.caixa, len(v.corretora.trades), v.ultimo_sinal_t, v.corretora.posicao)
            from mesa.vigia import Vigia

            v2 = Vigia(fonte, leitores_padrao(), v.cfg, tmp)                        # "processo novo"
            self.assertEqual((v2.corretora.caixa, len(v2.corretora.trades), v2.ultimo_sinal_t, v2.corretora.posicao), antes)
            n = len((Path(tmp) / "diario.jsonl").read_text().splitlines())
            v2.passo(fonte.agora)                                                   # não repete a vela já pensada
            self.assertEqual(len((Path(tmp) / "diario.jsonl").read_text().splitlines()), n)

    def test_kill_switch_persiste_e_bloqueia_ordens(self):
        from mesa.risco import ConfigRisco

        with tempfile.TemporaryDirectory() as tmp:
            v, fonte = self.montar(tmp, risco=ConfigRisco(drawdown_max=0.00001))
            for _ in range(250):
                fonte.avancar()
                v.passo(fonte.agora)
            self.assertTrue(v.guarda.desligado)
            from mesa.vigia import Vigia

            self.assertTrue(Vigia(fonte, leitores_padrao(), v.cfg, tmp).guarda.desligado)   # continua desligado após reiniciar
            self.assertIn("BLOQUEADA", (Path(tmp) / "eventos.log").read_text())

    def test_erro_de_rede_nao_derruba_o_laco(self):
        with tempfile.TemporaryDirectory() as tmp:
            v, fonte = self.montar(tmp)
            chamadas = {"n": 0}
            original = fonte.preco

            def instavel():
                chamadas["n"] += 1
                if chamadas["n"] == 1:
                    raise OSError("sem rede")
                return original()

            fonte.preco = instavel
            v.rodar(0, parar=lambda: chamadas["n"] >= 3, dormir=lambda s: None)
            self.assertIn("sem rede", (Path(tmp) / "eventos.log").read_text())
            self.assertTrue((Path(tmp) / "estado.json").exists())                   # os ciclos seguintes funcionaram


class TestFontesAoVivo(unittest.TestCase):
    def test_coinbase_ordena_pagina_e_descarta_vela_em_formacao(self):
        from mesa.fontes import FonteCoinbase

        agora = 1_700_000_000 + 5 * 3600 + 120                      # 2 min depois do início da 6ª vela
        base = (agora // 3600) * 3600
        todas = [[base - i * 3600, 99.0, 101.0, 100.0, 100.5 + i, 10] for i in range(-1, 700)]   # vem da mais nova para a mais velha; i=-1 é futura/em formação
        chamadas = []

        def transporte(url):
            chamadas.append(url)
            if "ticker" in url:
                return json.dumps({"price": "123.45"}).encode()
            return json.dumps(todas[:300] if len(chamadas) == 1 else todas[300:600]).encode()

        f = FonteCoinbase(transporte=transporte)
        velas = f.velas(400, agora)
        self.assertEqual(len(velas), 400)
        self.assertEqual([v.t for v in velas], sorted(v.t for v in velas))              # em ordem cronológica
        self.assertLessEqual(velas[-1].t + 3600, agora)                                  # nenhuma vela em formação
        self.assertEqual((velas[0].o, velas[0].h, velas[0].l), (100.0, 101.0, 99.0))      # ordem dos campos da Coinbase convertida
        self.assertEqual(f.preco(), 123.45)

    def test_binance_descarta_a_ultima_vela_em_formacao(self):
        from mesa.fontes import FonteBinance

        agora = 3600 * 100 + 50
        lote = [[(i * 3600) * 1000, "1", "2", "0.5", "1.5", "10", 0] for i in range(98, 101)]
        f = FonteBinance(transporte=lambda url: json.dumps(lote).encode())
        self.assertEqual([v.t for v in f.velas(5, agora)], [98 * 3600, 99 * 3600])        # a de 100*3600 ainda está aberta

    def test_cli_status_e_uma_vez(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                principal(["status", "--pasta", tmp])                                      # sem estado ainda
            from mesa.vigia import Vigia

            velas = dados.sintetico(900, seed=4)
            fonte = FonteFalsa(velas)
            fonte.agora = velas[-1].t + 3600
            Vigia(fonte, leitores_padrao(), Config(), tmp).passo(fonte.agora)
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                self.assertEqual(principal(["status", "--pasta", tmp]), 0)
            self.assertIn("SIMULAÇÃO", saida.getvalue())
            self.assertIn("fora do mercado", saida.getvalue())


class TestPaginaDaMesa(unittest.TestCase):
    CHAVE = "chave-de-teste-bem-longa-123"

    def preparar(self, tmp):
        import threading
        import urllib.request
        from http.cookiejar import CookieJar

        from mesa.painel import servidor
        from mesa.vigia import Vigia

        velas = dados.sintetico(900, seed=4)
        fonte = FonteFalsa(velas)
        fonte.agora = velas[-1].t + 3600
        Vigia(fonte, leitores_padrao(), Config(agregador="media"), tmp).passo(fonte.agora)
        srv = servidor(tmp, self.CHAVE, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.cliente = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def pedir(self, caminho):
        import urllib.error

        try:
            with self.cliente.open(self.base + caminho, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_saude_publica_e_o_resto_exige_chave(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.preparar(tmp)
            self.assertEqual(self.pedir("/saude"), (200, b'{"ok": true}'))
            self.assertEqual(self.pedir("/")[0], 401)
            self.assertEqual(self.pedir("/api/estado")[0], 401)
            self.assertEqual(self.pedir("/?k=errada")[0], 401)
            self.assertEqual(self.pedir(f"/?k={self.CHAVE}")[0], 200)                  # segue o redirecionamento já com o cookie
            status, corpo = self.pedir("/api/estado")
            d = json.loads(corpo)
            self.assertEqual(status, 200)
            self.assertIn("SIMULAÇÃO", d["estado"]["modo"])
            self.assertTrue(d["estado"]["ultimo_sinal"]["leituras"])                   # o que cada agente pensa
            self.assertTrue(d["eventos"])

    def test_pagina_avisa_que_e_simulacao_e_nao_expoe_outros_arquivos(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.preparar(tmp)
            self.pedir(f"/?k={self.CHAVE}")
            self.assertIn("SIMULAÇÃO".encode(), self.pedir("/")[1])
            for caminho in ("/velas.csv", "/estado.json", "/../etc/passwd"):
                self.assertEqual(self.pedir(caminho)[0], 404, caminho)

    def test_chave_curta_e_recusada(self):
        from mesa.painel import servidor

        with self.assertRaises(ValueError):
            servidor(".", "curta")

    def test_entrypoint_modo_mesa_e_modo_fabrica(self):
        import os
        import shutil
        import subprocess

        raiz = Path(__file__).resolve().parent.parent
        prefixo = []
        if os.getuid() == 0:
            if not shutil.which("setpriv"):
                self.skipTest("sem setpriv")
            prefixo = ["setpriv", "--reuid=nobody", "--regid=nogroup", "--clear-groups"]
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o777)
            (Path(tmp) / "bin").mkdir()
            shim = Path(tmp) / "bin" / "python"
            shim.write_text('#!/bin/sh\necho "ARGS:$*"\n')
            shim.chmod(0o755)

            def rodar(extra):
                env = {"PATH": f"{tmp}/bin:/usr/bin:/bin", "FABRICA_DADOS": f"{tmp}/d", "FABRICA_SAIDA": f"{tmp}/s", "FABRICA_CANAIS": f"{tmp}/c.json",
                       "FABRICA_EXEMPLO": str(raiz / "canais.example.json"), "MESA_PASTA": f"{tmp}/mesa", **extra}
                return subprocess.run(prefixo + ["env", "-i", *[f"{k}={v}" for k, v in env.items()], str(raiz / "docker/entrypoint.sh")],
                                      capture_output=True, text=True).stdout
            self.assertIn(f"ARGS:-m mesa vigiar --servir --fonte coinbase --pasta {tmp}/mesa", rodar({"FABRICA_MODO": "mesa"}))
            self.assertIn("ARGS:-m mesa vigiar --servir --fonte binance", rodar({"FABRICA_MODO": "mesa", "MESA_FONTE": "binance"}))
            self.assertIn("ARGS:-m fabrica painel --com-maestro", rodar({}))              # sem FABRICA_MODO volta à fábrica


class TestHistoricoEExternos(unittest.TestCase):
    def test_coinbase_historico_em_janelas_sem_buracos_e_sem_vela_aberta(self):
        agora = 1_700_000_000
        agora -= agora % 3600
        urls = []

        def transporte(url):
            urls.append(url)
            from datetime import datetime, timezone

            a = datetime.strptime(url.split("start=")[1].split("&")[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            b = datetime.strptime(url.split("end=")[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            return json.dumps([[int(t), 99.0, 101.0, 100.0, 100.5, 5] for t in range(int(b) - 3600, int(a) - 1, -3600)]).encode()

        progresso = []
        velas = dados.baixar_coinbase("BTC-USD", "1h", agora - 700 * 3600, agora, transporte, dormir=lambda s: None, progresso=progresso.append)
        self.assertEqual(len(velas), 700)
        self.assertEqual(len(urls), 3)                                                    # 300 + 300 + 100
        self.assertEqual([b.t - a.t for a, b in zip(velas, velas[1:])], [3600] * 699)     # sem buracos nem repetidas
        self.assertEqual(progresso[-1], 700)

    def test_lacunas_sao_contadas_e_preenchidas(self):
        v = dados.sintetico(10, seed=1)
        furado = v[:3] + v[6:]
        self.assertEqual(dados.contar_lacunas(furado), 3)
        cheio = dados.preencher_lacunas(furado)
        self.assertEqual((len(cheio), dados.contar_lacunas(cheio)), (10, 0))
        self.assertEqual((cheio[3].o, cheio[3].v), (v[2].c, 0.0))                          # repete o último fechamento, sem volume

    def test_serie_nunca_devolve_o_futuro(self):
        from mesa.externos import Serie

        s = Serie([(100, 1), (200, 2), (300, 3)])
        self.assertEqual(s.ate(250, 5), [(100, 1.0), (200, 2.0)])
        self.assertEqual(s.ate(99), [])
        s.adicionar([(200, 9)])                                                           # reenvio do mesmo instante substitui
        self.assertEqual(s.ate(250, 1), [(200, 9.0)])

    def test_medo_e_ganancia_com_24h_de_cautela(self):
        from mesa.externos import baixar_medo

        corpo = json.dumps({"data": [{"value": "20", "timestamp": "1000000"}, {"value": "80", "timestamp": "913600"}]}).encode()
        s = baixar_medo(lambda url: corpo)
        self.assertEqual(s.ate(1_000_000 + 86399), [(913600 + 86400, 80.0)])              # o valor de 1000000 ainda não conta
        self.assertEqual(s.ate(1_000_000 + 86400)[-1], (1_000_000 + 86400, 20.0))

    def test_funding_binance_e_bybit_paginam(self):
        from mesa.externos import baixar_funding_bybit, baixar_funding_binance

        chamadas = []

        def binance(url):
            chamadas.append(url)
            n = 1000 if len(chamadas) == 1 else 3
            base = 1_600_000_000 + (len(chamadas) - 1) * 1000 * 28800
            return json.dumps([{"fundingTime": (base + i * 28800) * 1000, "fundingRate": "0.0001"} for i in range(n)]).encode()

        self.assertEqual((len(baixar_funding_binance(desde=1_600_000_000, transporte=binance)), len(chamadas)), (1003, 2))

        def bybit(url):
            fim = int(url.split("endTime=")[1])
            itens = [{"fundingRateTimestamp": str(t), "fundingRate": "0.0002"} for t in range(fim - 1000, fim - 1000 - 200 * 8 * 3_600_000, -8 * 3_600_000)]
            return json.dumps({"result": {"list": itens[:200] if fim > 10 ** 12 else itens[:50]}}).encode()

        s = baixar_funding_bybit(desde=1_600_000_000, ate=1_700_000_000, transporte=bybit)
        self.assertGreater(len(s), 0)
        self.assertTrue(all(t >= 1_600_000_000 for t in s.t))

    def test_leitores_externos_nao_veem_o_futuro_e_inclinam_para_o_lado_certo(self):
        from mesa.externos import Serie
        from mesa.leitores import Funding, MedoGanancia

        velas = dados.sintetico(10, seed=1)
        agora = velas[-1].t + 3600
        medo = MedoGanancia(Serie([(agora - 10, 10.0), (agora + 5, 95.0)]))                # medo extremo agora; ganância só no futuro
        l = medo.ler(velas)
        self.assertGreater(l.p, 0.5)
        self.assertGreater(l.conf, 0.5)
        self.assertLess(MedoGanancia(Serie([(agora - 10, 95.0)])).ler(velas).p, 0.5)
        self.assertEqual(MedoGanancia(Serie()).ler(velas).conf, 0.0)
        pts = [(agora - 3600 * 8 * (40 - i), 0.0001 + (i % 3) * 1e-6) for i in range(40)]
        calmo = Funding(Serie(pts)).ler(velas)
        lotado = Funding(Serie(pts[:-1] + [(agora - 5, 0.01)])).ler(velas)                 # funding disparado: compradores lotando
        self.assertLess(lotado.p, 0.5)
        self.assertGreater(lotado.conf, calmo.conf)
        futuro = Funding(Serie(pts + [(agora + 99, 5.0)])).ler(velas)
        self.assertEqual((futuro.p, futuro.conf), (calmo.p, calmo.conf))                    # o ponto do futuro foi ignorado


class TestRelatorioEServico(unittest.TestCase):
    def velas(self):
        return dados.sintetico(3500, seed=2, modo="momentum")

    def test_relatorio_tem_tudo_e_vira_json(self):
        from mesa.relatorio import relatorio

        rel = relatorio(self.velas(), leitores_padrao(), Config(horizonte=6, taxa_bps=1, slippage_bps=0), meses_teste=1)
        json.dumps(rel)
        self.assertEqual(rel["periodo"]["lacunas_preenchidas"], 0)
        self.assertEqual(len(rel["completo"]), len(rel["teste"]))
        self.assertTrue(rel["veredito"] and rel["calibracao"]["n"] > 0)
        completo, teste = rel["completo"][0], rel["teste"][0]
        self.assertNotEqual(completo["retorno"], teste["retorno"])                         # o recorte é outro período
        self.assertLessEqual(teste["operacoes"], completo["operacoes"])

    def test_relatorio_tolera_historico_com_buracos(self):
        from mesa.relatorio import relatorio

        v = self.velas()
        furado = v[:1000] + v[1010:]
        rel = relatorio(furado, leitores_padrao(), Config(horizonte=6), meses_teste=1)
        self.assertEqual(rel["periodo"]["lacunas_preenchidas"], 10)

    def test_servico_baixa_calcula_e_guarda_so_quando_precisa(self):
        from mesa import servico

        v = self.velas()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(dados, "baixar_coinbase", return_value=v) as baixar:
            pasta = Path(tmp)
            self.assertTrue(servico.precisa_rodar(pasta))
            servico.rodar_uma_vez(pasta, "coinbase", "BTC-USD", "1h", 120, Config(horizonte=6), lambda velas: (leitores_padrao(), ["aviso de teste"]))
            baixar.assert_called_once()
            self.assertEqual(json.loads((pasta / "backtest.estado.json").read_text())["estado"], "pronto")
            self.assertEqual(json.loads((pasta / "backtest.json").read_text())["avisos"], ["aviso de teste"])
            self.assertTrue((pasta / "historico.csv").exists())
            self.assertFalse(servico.precisa_rodar(pasta))                                  # recém-feito
            import os

            velho = (pasta / "backtest.json").stat().st_mtime - 8 * 86400
            os.utime(pasta / "backtest.json", (velho, velho))
            self.assertTrue(servico.precisa_rodar(pasta))                                   # passou de uma semana: refaz

    def test_servico_em_segundo_plano_registra_erro_e_nao_morre(self):
        from mesa import servico

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(dados, "baixar_coinbase", side_effect=OSError("sem rede")):
            ciclos = {"n": 0}

            def dormir(s):
                ciclos["n"] += 1

            t = servico.iniciar_em_segundo_plano(tmp, "coinbase", "BTC-USD", "1h", 30, Config(), lambda v: (leitores_padrao(), []),
                                                 espera_s=0, dormir=dormir, parar=lambda: ciclos["n"] >= 2)
            t.join(5)
            est = json.loads((Path(tmp) / "backtest.estado.json").read_text())
            self.assertEqual(est["estado"], "erro")
            self.assertIn("sem rede", est["mensagem"])
            self.assertGreaterEqual(ciclos["n"], 2)                                          # tentou de novo em vez de morrer

    def test_pagina_traz_o_backtest_e_o_estado_dele(self):
        import threading
        import urllib.request
        from http.cookiejar import CookieJar

        from mesa import servico
        from mesa.painel import servidor

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(dados, "baixar_coinbase", return_value=self.velas()):
            servico.rodar_uma_vez(tmp, "coinbase", "BTC-USD", "1h", 60, Config(horizonte=6), lambda v: (leitores_padrao(), []))
            srv = servidor(tmp, "chave-de-teste-bem-longa-123", "127.0.0.1", 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            c = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            c.open(f"{base}/?k=chave-de-teste-bem-longa-123", timeout=5).read()
            d = json.loads(c.open(f"{base}/api/estado", timeout=5).read())
            self.assertEqual(d["backtest_estado"]["estado"], "pronto")
            self.assertEqual(len(d["backtest"]["completo"]), len(d["backtest"]["teste"]))
            self.assertIn("grafico", d["backtest"])


class TestCliExtras(unittest.TestCase):
    def test_extras_que_falham_viram_aviso_e_nao_derrubam(self):
        import argparse

        from mesa import externos
        from mesa.cli import montar_leitores

        a = argparse.Namespace(medo=True, funding="binance")
        with mock.patch.object(externos, "baixar_medo", side_effect=OSError("bloqueado")), \
                mock.patch.dict(externos.FUNDING, {"binance": mock.Mock(side_effect=OSError("HTTP 451"))}):
            lista, avisos = montar_leitores(a, dados.sintetico(50, seed=1))
        self.assertEqual(len(lista), len(leitores_padrao()))                                # segue só com os leitores padrão
        self.assertEqual(len(avisos), 2)
        self.assertIn("bloqueado", avisos[0])
        self.assertIn("451", avisos[1])

    def test_leitores_extras_entram_quando_os_dados_chegam(self):
        import argparse

        from mesa import externos
        from mesa.cli import montar_leitores

        with mock.patch.object(externos, "baixar_medo", return_value=externos.Serie([(1, 40.0)])):
            lista, avisos, atual = montar_leitores(argparse.Namespace(medo=True, funding=None), None, com_atualizadores=True)
        self.assertEqual(lista[-1].nome, "medo e ganância")
        self.assertEqual((avisos, len(atual)), ([], 1))

    def test_backtest_cli_salva_json_e_baixar_usa_a_coinbase(self):
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp:
            csv, js = str(Path(tmp) / "h.csv"), str(Path(tmp) / "r.json")
            with mock.patch.object(dados, "baixar_coinbase", return_value=dados.sintetico(900, seed=2)) as m, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(principal(["baixar", "--desde", "2022-01-01", "--saida", csv]), 0)
            self.assertEqual(m.call_args.args[0], "BTC-USD")
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                self.assertEqual(principal(["backtest", "--dados", csv, "--horizonte", "6", "--meses-teste", "1", "--json", js]), 0)
            self.assertIn("TESTE: ÚLTIMOS 1 MESES", saida.getvalue())
            self.assertIn("VEREDITO", saida.getvalue())
            self.assertIn("completo", json.loads(Path(js).read_text()))

    def test_vigia_segue_quando_um_dado_externo_falha(self):
        from mesa.vigia import Vigia

        with tempfile.TemporaryDirectory() as tmp:
            velas = dados.sintetico(900, seed=4)
            f = FonteFalsa(velas)
            f.agora = velas[-1].t + 3600
            v = Vigia(f, leitores_padrao(), Config(agregador="media"), tmp, atualizadores=[lambda: (_ for _ in ()).throw(OSError("API fora"))])
            eventos = v.passo(f.agora)
            self.assertTrue(any("API fora" in e for e in eventos))
            self.assertTrue((Path(tmp) / "estado.json").exists())


class TestIdentificacaoHttp(unittest.TestCase):
    def test_todas_as_requisicoes_se_identificam(self):
        """Regressão: o histórico levou HTTP 403 da Coinbase no servidor porque não enviava User-Agent."""
        from mesa import dados as d, fontes

        for funcao in (d._http, fontes._http):
            visto = {}

            class Resp:
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def read(self): return b"[]"

            def falso(req, timeout=None):
                visto["ua"] = req.get_header("User-agent")
                return Resp()

            with mock.patch("urllib.request.urlopen", falso):
                funcao("https://exemplo.test/x")
            self.assertTrue(visto["ua"] and "python-urllib" not in visto["ua"].lower(), funcao.__module__)


class TestRelatorioNoLog(unittest.TestCase):
    def test_mostra_o_relatorio_guardado_ao_subir_e_permite_forcar_recalculo(self):
        import contextlib
        import io
        import os

        from mesa import servico

        v = dados.sintetico(2500, seed=2, modo="momentum")
        with tempfile.TemporaryDirectory() as tmp:
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                self.assertFalse(servico.mostrar_existente(Path(tmp)))                    # nada guardado ainda: não imprime
            with mock.patch.object(dados, "baixar_coinbase", return_value=v), contextlib.redirect_stdout(io.StringIO()) as log:
                servico.rodar_uma_vez(tmp, "coinbase", "BTC-USD", "1h", 60, Config(horizonte=6), lambda vv: (leitores_padrao(), []))
            self.assertIn("RESULTADO", log.getvalue())
            self.assertIn("VEREDITO", log.getvalue())
            with contextlib.redirect_stdout(io.StringIO()) as log2:
                self.assertTrue(servico.mostrar_existente(Path(tmp)))
            self.assertIn("ÚLTIMO RELATÓRIO GUARDADO", log2.getvalue())
            self.assertIn("PERÍODO COMPLETO", log2.getvalue())

            chamadas = []
            with mock.patch.object(servico, "rodar_uma_vez", side_effect=lambda *a, **k: chamadas.append(1)), \
                    mock.patch.dict(os.environ, {"MESA_BACKTEST_REFAZER": "1"}), contextlib.redirect_stdout(io.StringIO()):
                ciclos = {"n": 0}
                t = servico.iniciar_em_segundo_plano(tmp, "coinbase", "BTC-USD", "1h", 60, Config(), lambda vv: ([], []),
                                                     espera_s=0, dormir=lambda s: ciclos.__setitem__("n", ciclos["n"] + 1), parar=lambda: ciclos["n"] >= 2)
                t.join(5)
            self.assertEqual(len(chamadas), 1)                                            # recalculou uma vez, mesmo com relatório recente
