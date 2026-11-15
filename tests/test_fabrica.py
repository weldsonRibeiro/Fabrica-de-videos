import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from fabrica.armazem import Armazem
from fabrica.jogo import Carteira
from fabrica.maestro import Maestro, aprovar
from fabrica.modelos import Canal, Etapa, Status
from fabrica.pipeline import Pipeline
from fabrica.provedores.falso import ProvedorFalso, PublicadorFalso

CANAIS = [
    Canal("a", "Canal A", "x", "05:30", ["tema A1", "tema A2"]),
    Canal("b", "Canal B", "y", "07:00", ["tema B1"]),
]
DIA = date(2026, 11, 16)


class Base(unittest.TestCase):
    def montar(self, provedor=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        armazem = Armazem(Path(self.tmp.name))
        pipeline = Pipeline(provedor or ProvedorFalso(), armazem)
        return armazem, Maestro(armazem, pipeline, CANAIS, PublicadorFalso())


class TestAgenda(Base):
    def test_um_video_por_canal_no_horario_e_idempotente(self):
        armazem, maestro = self.montar()
        criados = maestro.montar_agenda(DIA)
        self.assertEqual([v.producao_em.strftime("%H:%M") for v in criados], ["05:30", "07:00"])
        self.assertEqual(maestro.montar_agenda(DIA), [])
        self.assertEqual(len(armazem.listar_videos()), 2)

    def test_so_produz_na_hora_de_cada_canal(self):
        armazem, maestro = self.montar()
        maestro.tick(datetime(2026, 11, 16, 5, 29))
        self.assertTrue(all(v.status is Status.AGENDADO for v in armazem.listar_videos()))
        maestro.tick(datetime(2026, 11, 16, 5, 30))
        status = {v.canal_id: v.status for v in armazem.listar_videos()}
        self.assertEqual(status["a"], Status.AGUARDANDO_APROVACAO)
        self.assertEqual(status["b"], Status.AGENDADO)

    def test_a_noite_o_dia_seguinte_ja_esta_na_agenda(self):
        armazem, maestro = self.montar()
        maestro.tick(datetime(2026, 11, 16, 21, 0))
        ids = {v.id for v in armazem.listar_videos()}
        self.assertIn("2026-11-17-a", ids)


class TestRetomada(Base):
    def test_limite_pausa_e_retoma_da_etapa_onde_parou(self):
        provedor = ProvedorFalso(limites={Etapa.CENAS: 1})
        armazem, maestro = self.montar(provedor)
        t0 = datetime(2026, 11, 16, 5, 30)
        maestro.tick(t0)
        v = armazem.carregar_video("2026-11-16-a")
        self.assertEqual(v.status, Status.PAUSADO)
        self.assertEqual(v.retomar_em, t0 + timedelta(hours=1))
        self.assertEqual(set(v.artefatos), {"pesquisa", "roteiro", "narracao"})
        custo_antes = v.custo

        maestro.tick(t0 + timedelta(minutes=30))  # ainda cedo: nada muda
        self.assertEqual(armazem.carregar_video(v.id).status, Status.PAUSADO)

        maestro.tick(t0 + timedelta(hours=1))
        v = armazem.carregar_video(v.id)
        self.assertEqual(v.status, Status.AGUARDANDO_APROVACAO)
        self.assertGreater(v.custo, custo_antes)  # etapas já feitas não foram repetidas/cobradas de novo
        self.assertAlmostEqual(v.custo, 6.5)

    def test_falha_repetida_marca_como_falhou(self):
        class Quebrado:
            def executar(self, etapa, video):
                raise RuntimeError("boom")

        armazem, maestro = self.montar(Quebrado())
        t = datetime(2026, 11, 16, 5, 30)
        for i in range(3):
            maestro.tick(t + timedelta(minutes=10 * i))
        v = armazem.carregar_video("2026-11-16-a")
        self.assertEqual(v.status, Status.FALHOU)
        self.assertIn("boom", v.erro)


class TestAprovacaoEJogo(Base):
    def test_fluxo_completo_do_dono(self):
        armazem, maestro = self.montar()
        t = datetime(2026, 11, 16, 5, 30)
        maestro.tick(t)
        v = armazem.carregar_video("2026-11-16-a")
        self.assertEqual(len(v.pacote["titulos"]), 3)
        self.assertEqual(len(v.pacote["shorts"]), 3)
        self.assertEqual(len(v.pacote["thumbnails"]), 3)

        aprovar(armazem, v.id, 1, 2, datetime(2026, 11, 17, 18, 0))
        maestro.tick(t + timedelta(minutes=1))
        v = armazem.carregar_video(v.id)
        self.assertEqual(v.status, Status.AGENDADO_NO_CANAL)
        self.assertEqual(v.id_externo, "falso-2026-11-16-a")
        self.assertEqual(v.escolha["titulo"], v.pacote["titulos"][1])

    def test_nao_aprova_video_que_nao_esta_pronto(self):
        armazem, maestro = self.montar()
        maestro.montar_agenda(DIA)
        with self.assertRaises(ValueError):
            aprovar(armazem, "2026-11-16-a", 0, 0, datetime(2026, 11, 17, 18, 0))

    def test_despesa_por_video_e_moeda_por_view_sem_duplicar(self):
        armazem, maestro = self.montar()
        t = datetime(2026, 11, 16, 5, 30)
        maestro.tick(t)
        maestro.tick(t + timedelta(minutes=1))  # não cobra duas vezes
        carteira = Carteira.carregar(armazem)
        self.assertEqual(carteira.saldo, -6.5)

        self.assertEqual(carteira.registrar_views("2026-11-16-a", 5000), 50.0)
        self.assertEqual(carteira.registrar_views("2026-11-16-a", 5000), 0.0)
        self.assertEqual(carteira.registrar_views("2026-11-16-a", 6000), 10.0)
        self.assertEqual(carteira.saldo, 53.5)


if __name__ == "__main__":
    unittest.main()
