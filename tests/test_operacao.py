import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from fabrica import doctor
from fabrica.env import carregar_env
from fabrica.fuso import agora_local


class TestEnv(unittest.TestCase):
    def test_le_env_sem_sobrescrever_e_ignora_vazios(self):
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / ".env"
            arq.write_text(
                '# comentário\nA_CHAVE="valor com espaço"\nB_CHAVE=simples # comentário no fim\n'
                "export C_CHAVE='aspas simples'\nD_VAZIA=\nJA_DEFINIDA=do-arquivo\nlinha sem igual\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"JA_DEFINIDA": "do-ambiente"}, clear=False):
                definidas = carregar_env(arq)
                self.assertEqual(os.environ["A_CHAVE"], "valor com espaço")
                self.assertEqual(os.environ["B_CHAVE"], "simples")
                self.assertEqual(os.environ["C_CHAVE"], "aspas simples")
                self.assertNotIn("D_VAZIA", os.environ)
                self.assertEqual(os.environ["JA_DEFINIDA"], "do-ambiente")  # o ambiente vence o arquivo
                self.assertEqual(sorted(definidas), ["A_CHAVE", "B_CHAVE", "C_CHAVE"])
                for k in definidas:
                    del os.environ[k]

    def test_arquivo_inexistente(self):
        self.assertEqual(carregar_env("/nao/existe/.env"), [])


class TestFuso(unittest.TestCase):
    def test_agenda_no_horario_do_dono_e_nao_no_do_servidor(self):
        with mock.patch.dict(os.environ, {"FABRICA_FUSO": "Pacific/Kiritimati"}):  # UTC+14
            hora_kiribati = agora_local()
        with mock.patch.dict(os.environ, {"FABRICA_FUSO": "Pacific/Pago_Pago"}):   # UTC-11
            hora_samoa = agora_local()
        self.assertGreaterEqual((hora_kiribati - hora_samoa).total_seconds(), 24 * 3600 - 5)
        self.assertIsNone(hora_kiribati.tzinfo)


def canais_validos(tmp, extra=None):
    caminho = Path(tmp) / "canais.json"
    caminho.write_text(json.dumps([{"id": "meu-canal", "nome": "X", "inicio_producao": "05:30", "temas": ["t"], **(extra or {})}]))
    return str(caminho)


def rodar(tmp, env, provedor="falso", publicador="falso", canais=None, which=lambda n: "/usr/bin/" + n):
    return doctor.verificar(canais=canais or canais_validos(tmp), dados=f"{tmp}/dados", saida=f"{tmp}/saida",
                            provedor=provedor, publicador=publicador, env=env, which=which)


def niveis(resultados):
    return [n for n, _ in resultados]


class TestDoctor(unittest.TestCase):
    CHAVE = {"FABRICA_PAINEL_CHAVE": "x" * 20}

    def test_simulacao_ok_com_avisos(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = rodar(tmp, self.CHAVE)
            self.assertNotIn(doctor.ERRO, niveis(r))
            self.assertIn(doctor.AVISO, niveis(r))  # provedor/publicador falsos

    def test_sem_chave_do_painel_e_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn(doctor.ERRO, niveis(rodar(tmp, {})))

    def test_modo_real_aponta_exatamente_o_que_falta(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = rodar(tmp, self.CHAVE, provedor="real", publicador="youtube", which=lambda n: None)
            textos = " | ".join(t for n, t in r if n == doctor.ERRO)
            self.assertIn("ffmpeg", textos)
            self.assertIn("OPENAI_API_KEY", textos)
            self.assertIn("YOUTUBE_CLIENT_ID", textos)
            self.assertIn("YOUTUBE_REFRESH_TOKEN_MEU_CANAL", textos)  # "-" vira "_", maiúsculas
            self.assertIn("youtube-autorizar --canal meu-canal", textos)

    def test_modo_real_completo_nao_tem_erro_e_nao_vaza_segredo(self):
        env = {**self.CHAVE, "ANTHROPIC_API_KEY": "sk-segredo-1", "OPENAI_API_KEY": "sk-segredo-2",
               "YOUTUBE_CLIENT_ID": "id", "YOUTUBE_CLIENT_SECRET": "sk-segredo-3", "YOUTUBE_REFRESH_TOKEN_MEU_CANAL": "sk-segredo-4"}
        with tempfile.TemporaryDirectory() as tmp:
            r = rodar(tmp, env, provedor="real", publicador="youtube")
            self.assertNotIn(doctor.ERRO, niveis(r))
            self.assertNotIn("segredo", " ".join(t for _, t in r))

    def test_canais_invalidos(self):
        with tempfile.TemporaryDirectory() as tmp:
            erros = [t for n, t in rodar(tmp, self.CHAVE, canais=canais_validos(tmp, {"inicio_producao": "5h30", "temas": []})) if n == doctor.ERRO]
            self.assertTrue(any("HH:MM" in t and "sem temas" in t for t in erros))
            self.assertIn(doctor.ERRO, niveis(rodar(tmp, self.CHAVE, canais=f"{tmp}/nao-existe.json")))

    def test_codigo_de_saida(self):
        self.assertEqual(doctor.imprimir([(doctor.OK, "a"), (doctor.AVISO, "b")]), 0)
        self.assertEqual(doctor.imprimir([(doctor.ERRO, "c")]), 1)


class TestSaude(unittest.TestCase):
    def test_saude_nao_exige_chave_e_nao_revela_nada(self):
        import threading
        import urllib.request

        from fabrica.armazem import Armazem
        from fabrica.painel import Painel

        with tempfile.TemporaryDirectory() as tmp:
            srv = Painel(Armazem(tmp), [], "chave-de-teste-bem-longa-123", Path(tmp)).servidor("127.0.0.1", 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/saude", timeout=5) as r:
                self.assertEqual((r.status, json.loads(r.read())), (200, {"ok": True}))


if __name__ == "__main__":
    unittest.main()
