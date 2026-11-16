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


class TestVercelConfigurar(unittest.TestCase):
    def rodar(self, origem):
        import shutil
        import subprocess

        raiz = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "scripts").mkdir()
            (Path(tmp) / "vercel").mkdir()
            shutil.copy(raiz / "scripts/vercel-configurar.sh", Path(tmp) / "scripts")
            shutil.copy(raiz / "vercel/vercel.template.json", Path(tmp) / "vercel")
            r = subprocess.run(["bash", str(Path(tmp) / "scripts/vercel-configurar.sh"), origem], capture_output=True, text=True)
            arquivo = Path(tmp) / "vercel/vercel.json"
            return r.returncode, (json.loads(arquivo.read_text()) if arquivo.exists() else None)

    def test_gera_repasse_para_o_servidor(self):
        codigo, cfg = self.rodar("https://minha-fabrica.up.railway.app")
        self.assertEqual(codigo, 0)
        self.assertEqual(cfg["rewrites"], [{"source": "/(.*)", "destination": "https://minha-fabrica.up.railway.app/$1"}])
        self.assertIsNone(cfg["framework"])

    def test_recusa_http_caminho_e_laco(self):
        for ruim in ("http://x.com", "https://x.com/painel", "https://x.com/", "https://meu.vercel.app", ""):
            codigo, cfg = self.rodar(ruim)
            self.assertNotEqual(codigo, 0, ruim)
            self.assertIsNone(cfg)

    def test_template_nao_deixa_o_painel_ser_indexado(self):
        raiz = Path(__file__).resolve().parent.parent
        modelo = json.loads((raiz / "vercel/vercel.template.json").read_text())
        chaves = {h["key"] for regra in modelo["headers"] for h in regra["headers"]}
        self.assertIn("X-Robots-Tag", chaves)


class TestPerfisDeCanal(unittest.TestCase):
    PERFIL = {"voz": "nova", "estilo_voz": "animada", "tom": "bem-humorado", "publico": "jovens", "estilo_visual": "pixel art",
              "evitar": ["política"], "cenas": 5, "categoria_youtube": "28", "idioma": "pt-BR"}

    def canal(self, perfil=None):
        from fabrica.modelos import Canal
        return Canal.de_dict({"id": "c", "nome": "C", "nicho": "n", "inicio_producao": "06:00", "temas": ["t"], "perfil": perfil or {}})

    def test_perfil_vai_do_canal_para_o_video_e_sobrevive_ao_disco(self):
        from fabrica.armazem import Armazem
        from fabrica.maestro import Maestro
        from fabrica.pipeline import Pipeline
        from fabrica.provedores.falso import ProvedorFalso, PublicadorFalso
        from datetime import date

        with tempfile.TemporaryDirectory() as tmp:
            a = Armazem(tmp)
            Maestro(a, Pipeline(ProvedorFalso(), a), [self.canal(self.PERFIL)], PublicadorFalso()).montar_agenda(date(2026, 11, 16))
            v = a.carregar_video("2026-11-16-c")
            self.assertEqual(v.perfil, self.PERFIL)
            self.assertEqual(self.canal().perfil.para_dict(), {})  # perfil vazio não polui o JSON

    def test_campos_desconhecidos_sao_ignorados_e_tipos_normalizados(self):
        from fabrica.modelos import Perfil

        p = Perfil.de_dict({"voz": "onyx", "inventado": 1, "cenas": "8", "categoria_youtube": 27})
        self.assertEqual((p.voz, p.cenas, p.categoria_youtube), ("onyx", 8, "27"))

    def test_roteiro_usa_tom_publico_evitar_e_numero_de_cenas_do_perfil(self):
        from fabrica.config import Config
        from fabrica.modelos import Perfil
        from fabrica.provedores.claude import ClienteClaude

        class Capta:
            def __init__(self):
                self.prompts = []

            def _chamar(self, prompt, **kw):
                self.prompts.append(prompt)
                raise RuntimeError("só capturar o prompt")

        c = ClienteClaude(Config(cenas=12), cliente=object())
        capta = Capta()
        c._chamar = capta._chamar
        with self.assertRaises(RuntimeError):
            c.roteirizar("tema", "finanças", "dossiê", Perfil.de_dict(self.PERFIL))
        prompt = capta.prompts[0]
        self.assertIn("5 cenas", prompt)                     # o perfil manda no nº de cenas (não as 12 padrão)
        self.assertIn("bem-humorado", prompt)
        self.assertIn("jovens", prompt)
        self.assertIn("Nunca use nem aborde: política", prompt)
        self.assertIn("pixel art", prompt)

    def test_voz_estilo_visual_no_provedor_real(self):
        import base64
        import shutil
        import subprocess

        if not shutil.which("ffmpeg"):
            self.skipTest("sem ffmpeg")
        from fabrica.config import Config
        from fabrica.modelos import Video
        from fabrica.provedores.openai_http import ClienteOpenAI
        from fabrica.provedores.real import ProvedorReal

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=d=1", str(raiz / "v.mp3")], check=True)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=64x64", "-frames:v", "1", str(raiz / "i.png")], check=True)
            png = base64.b64encode((raiz / "i.png").read_bytes()).decode()
            enviados = []

            def transporte(url, headers, corpo):
                enviados.append((url.rsplit("/", 1)[-1], corpo))
                return (raiz / "v.mp3").read_bytes() if url.endswith("speech") else json.dumps({"data": [{"b64_json": png}]}).encode()

            prov = ProvedorReal(Config(openai_key="k", saida=raiz / "s"), claude=object(), openai=ClienteOpenAI("k", transporte))
            v = Video("v1", "c", "t", datetime(2026, 11, 16, 5, 30), perfil=self.PERFIL)
            v.artefatos["roteiro"] = {"cenas": [{"narracao": "oi", "prompt_imagem": "um castelo"}], "thumbnails": ["um herói"]}
            prov.executar(__import__("fabrica.modelos", fromlist=["Etapa"]).Etapa.NARRACAO, v)
            prov.executar(__import__("fabrica.modelos", fromlist=["Etapa"]).Etapa.CENAS, v)
            voz = next(c for n, c in enviados if n == "speech")
            self.assertEqual((voz["voice"], voz["instructions"]), ("nova", "animada"))
            imagem = next(c for n, c in enviados if n == "generations")
            self.assertEqual(imagem["prompt"], "pixel art. um castelo")

    def test_youtube_usa_categoria_e_idioma_do_perfil(self):
        from tests.test_youtube import TestPublicadorYouTube, YouTubeFalso  # reaproveita o YouTube simulado
        t = TestPublicadorYouTube("test_agenda_video_thumbnail_e_shorts")
        t.setUp()
        try:
            t.video.perfil = {"categoria_youtube": "28", "idioma": "en-US"}
            t.publicador().agendar(t.video)
            snippet = t.http.metadados["https://upload/1"]["snippet"]
            self.assertEqual((snippet["categoryId"], snippet["defaultLanguage"]), ("28", "en-US"))
        finally:
            t.doCleanups()

    def test_doctor_valida_perfis(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruim = canais_validos(tmp, {"perfil": {"cenas": 99, "categoria_youtube": "educacao", "voz": "robo", "inventado": 1}})
            r = rodar(tmp, {"FABRICA_PAINEL_CHAVE": "x" * 20}, canais=ruim)
            erros = " ".join(t for n, t in r if n == doctor.ERRO)
            avisos = " ".join(t for n, t in r if n == doctor.AVISO)
            self.assertIn("perfil.cenas", erros)
            self.assertIn("perfil.categoria_youtube", erros)
            self.assertIn("desconhecido", erros)
            self.assertIn("voz 'robo'", avisos)
            bom = canais_validos(tmp, {"perfil": TestPerfisDeCanal.PERFIL})
            self.assertNotIn(doctor.ERRO, niveis(rodar(tmp, {"FABRICA_PAINEL_CHAVE": "x" * 20}, canais=bom)))
