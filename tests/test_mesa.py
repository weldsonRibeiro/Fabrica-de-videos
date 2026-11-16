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
