import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fabrica.armazem import Armazem
from fabrica.maestro import Maestro
from fabrica.modelos import Canal, Status, Video
from fabrica.pipeline import Pipeline
from fabrica.provedores.base import LimiteAtingido
from fabrica.provedores.falso import ProvedorFalso
from fabrica.provedores.youtube import ConfigYouTube, ErroYouTube, PublicadorYouTube, segundos_ate_virada_da_cota

AGORA = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class YouTubeFalso:
    """Simula token, upload resumível, thumbnails.set e cota."""

    def __init__(self):
        self.chamadas = []
        self.recebido = {}        # sessao -> bytes
        self.metadados = {}       # sessao -> dict
        self.cair_apos_pedaco = 0  # simula 5xx no N-ésimo PUT de pedaço
        self.cota_estourada = False
        self._puts = 0

    def __call__(self, metodo, url, headers, corpo):
        self.chamadas.append((metodo, url.split("?")[0]))
        if url.endswith("/token"):
            return 200, {}, json.dumps({"access_token": "tok"}).encode()
        if "thumbnails/set" in url:
            self.thumb = (url, corpo)
            return 200, {}, b"{}"
        if metodo == "POST" and "upload/youtube/v3/videos" in url:
            if self.cota_estourada:
                erro = {"error": {"errors": [{"reason": "quotaExceeded"}]}}
                return 403, {}, json.dumps(erro).encode()
            sessao = f"https://upload/{len(self.metadados) + 1}"
            self.metadados[sessao] = json.loads(corpo)
            self.recebido[sessao] = b""
            return 200, {"location": sessao}, b""
        # PUT na sessão
        total = int(headers["Content-Range"].split("/")[1])
        atual = len(self.recebido[url])
        if headers["Content-Range"].startswith("bytes */"):
            return self._estado(url, total, atual)
        self._puts += 1
        if self.cair_apos_pedaco and self._puts == self.cair_apos_pedaco:
            return 503, {}, b"indisponivel"
        inicio = int(headers["Content-Range"].split()[1].split("-")[0])
        assert inicio == atual, f"offset errado: {inicio} != {atual}"
        self.recebido[url] += corpo
        return self._estado(url, total, len(self.recebido[url]))

    def _estado(self, url, total, atual):
        if atual >= total:
            return 200, {}, json.dumps({"id": f"yt{url[-1]}"}).encode()
        return 308, ({"range": f"bytes=0-{atual - 1}"} if atual else {}), b""


class TestPublicadorYouTube(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        (self.raiz / "video.mp4").write_bytes(b"v" * 100)
        (self.raiz / "s1.mp4").write_bytes(b"s" * 10)
        (self.raiz / "s2.mp4").write_bytes(b"t" * 10)
        (self.raiz / "t.jpg").write_bytes(b"jpg")
        self.http = YouTubeFalso()
        self.video = Video("2026-11-16-a", "canal-a", "tema", datetime(2026, 11, 16, 5, 30))
        self.video.pacote = {"video": str(self.raiz / "video.mp4"), "descricao": "desc",
                             "shorts": [str(self.raiz / "s1.mp4"), str(self.raiz / "s2.mp4")]}
        self.video.artefatos = {"roteiro": {"shorts": [{"titulo": "Short um"}, {"titulo": "Short dois"}]}}
        self.video.escolha = {"titulo": "Meu título", "thumbnail": str(self.raiz / "t.jpg"),
                              "publicar_em": "2026-11-17T18:00:00"}

    def publicador(self):
        cfg = ConfigYouTube("id", "segredo", {"canal-a": "refresh"})
        return PublicadorYouTube(cfg, saida=self.raiz / "saida", transporte=self.http, agora=lambda: AGORA)

    def test_agenda_video_thumbnail_e_shorts(self):
        video_id = self.publicador().agendar(self.video)
        self.assertEqual(video_id, "yt1")
        principal = self.http.metadados["https://upload/1"]
        self.assertEqual(principal["status"]["privacyStatus"], "private")
        self.assertEqual(principal["status"]["publishAt"], "2026-11-17T21:00:00Z")  # 18h de Brasília em UTC
        self.assertTrue(principal["status"]["containsSyntheticMedia"])
        self.assertEqual(principal["snippet"]["title"], "Meu título")
        self.assertEqual(self.http.recebido["https://upload/1"], b"v" * 100)
        self.assertIn("videoId=yt1", self.http.thumb[0])
        s1 = self.http.metadados["https://upload/2"]
        self.assertEqual(s1["snippet"]["title"], "Short um #Shorts")
        self.assertEqual(s1["status"]["publishAt"], "2026-11-18T09:00:00Z")  # +12h
        self.assertEqual(self.http.metadados["https://upload/3"]["status"]["publishAt"], "2026-11-18T21:00:00Z")

    def test_horario_no_passado_vira_agora_mais_10_minutos(self):
        self.video.escolha["publicar_em"] = "2026-11-10T08:00:00"
        self.publicador().agendar(self.video)
        self.assertEqual(self.http.metadados["https://upload/1"]["status"]["publishAt"], "2026-11-16T12:10:00Z")

    def test_upload_cai_no_meio_e_retoma_de_onde_parou(self):
        import fabrica.provedores.youtube as yt

        yt.TAMANHO_PEDACO, original = 40, yt.TAMANHO_PEDACO
        self.addCleanup(setattr, yt, "TAMANHO_PEDACO", original)
        self.http.cair_apos_pedaco = 2  # 1º pedaço (40 B) passa, o 2º dá 503
        with self.assertRaises(ErroYouTube):
            self.publicador().agendar(self.video)
        self.assertEqual(len(self.http.recebido["https://upload/1"]), 40)

        self.assertEqual(self.publicador().agendar(self.video), "yt1")
        self.assertEqual(self.http.recebido["https://upload/1"], b"v" * 100)  # completo, sem recomeçar
        self.assertEqual(len(self.http.metadados), 3)  # nenhuma sessão extra para o vídeo principal

    def test_falha_nos_shorts_nao_sobe_o_principal_de_novo(self):
        self.http.cota_estourada = False
        pub = self.publicador()
        original = self.http.__call__

        def quebra_no_short(metodo, url, headers, corpo):
            if metodo == "POST" and "upload/youtube/v3/videos" in url and len(self.http.metadados) == 1:
                return 500, {}, b"erro"
            return original(metodo, url, headers, corpo)

        pub._http = quebra_no_short
        with self.assertRaises(ErroYouTube):
            pub.agendar(self.video)
        pub._http = original
        pub.agendar(self.video)
        videos_criados = [m for m in self.http.metadados.values()]
        self.assertEqual(len(videos_criados), 3)  # principal + 2 shorts, sem duplicar

    def test_cota_estourada_vira_limite_ate_a_virada(self):
        self.http.cota_estourada = True
        with self.assertRaises(LimiteAtingido) as ctx:
            self.publicador().agendar(self.video)
        # 12:00 UTC = 04:00 PST → virada 00:05 PST do dia seguinte = 20h05 depois
        self.assertEqual(ctx.exception.esperar, timedelta(hours=20, minutes=5))

    def test_canal_sem_token(self):
        self.video.canal_id = "outro"
        with self.assertRaises(ErroYouTube) as ctx:
            self.publicador().agendar(self.video)
        self.assertIn("YOUTUBE_REFRESH_TOKEN_OUTRO", str(ctx.exception))

    def test_config_le_token_por_canal(self):
        env = {"YOUTUBE_CLIENT_ID": "i", "YOUTUBE_CLIENT_SECRET": "s", "YOUTUBE_REFRESH_TOKEN_MEU_CANAL": "r"}
        cfg = ConfigYouTube.do_ambiente(["meu-canal", "sem-token"], env)
        self.assertEqual(cfg.refresh_tokens, {"meu-canal": "r"})
        with self.assertRaises(ErroYouTube):
            ConfigYouTube.do_ambiente(["x"], {})

    def test_virada_da_cota_em_horario_de_verao(self):
        agora = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)  # 05:00 PDT
        self.assertEqual(segundos_ate_virada_da_cota(agora), timedelta(hours=19, minutes=5))


class TestAutorizacao(unittest.TestCase):
    def test_fluxo_oauth_local_devolve_refresh_token(self):
        import threading
        import urllib.parse
        import urllib.request

        from fabrica.provedores.youtube import autorizar

        urls, resultado = [], {}

        def trocar_codigo(metodo, url, headers, corpo):
            resultado["corpo"] = urllib.parse.parse_qs(corpo.decode())
            return 200, {}, json.dumps({"access_token": "a", "refresh_token": "REFRESH"}).encode()

        def abrir(texto):
            urls.append(texto)

        t = threading.Thread(target=lambda: resultado.setdefault("token", autorizar("cid", "seg", 8766, abrir, trocar_codigo)))
        t.start()
        for _ in range(50):  # espera o servidor local subir
            if urls:
                break
            threading.Event().wait(0.05)
        link = next(l for l in urls[0].split() if l.startswith("https://accounts.google.com"))
        estado = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)["state"][0]
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:8766/?code=CODIGO&state={estado}", timeout=2).read()
                break
            except OSError:
                threading.Event().wait(0.05)
        t.join(5)
        self.assertEqual(resultado["token"], "REFRESH")
        self.assertEqual(resultado["corpo"]["code"], ["CODIGO"])
        self.assertIn("access_type=offline", link)


class QuebradoNaCota:
    def __init__(self, vezes=1, erro=None):
        self.vezes, self.erro, self.subidos = vezes, erro, []

    def agendar(self, video):
        if self.vezes > 0:
            self.vezes -= 1
            raise self.erro
        self.subidos.append(video.id)
        return "yt-ok"


class TestMaestroPublicacaoResiliente(unittest.TestCase):
    def montar(self, publicador):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        armazem = Armazem(Path(self.tmp.name))
        canais = [Canal("a", "A", "x", "05:30", ["t"])]
        m = Maestro(armazem, Pipeline(ProvedorFalso(), armazem), canais, publicador)
        t = datetime(2026, 11, 16, 5, 30)
        m.tick(t)
        v = armazem.carregar_video("2026-11-16-a")
        v.escolha = {"titulo": "x", "thumbnail": "t", "publicar_em": "2026-11-17T18:00"}
        v.status = Status.APROVADO
        armazem.salvar_video(v)
        return armazem, m, t

    def test_cota_estourada_mantem_aprovado_e_tenta_depois(self):
        pub = QuebradoNaCota(1, LimiteAtingido(timedelta(hours=20)))
        armazem, m, t = self.montar(pub)
        m.tick(t + timedelta(minutes=1))
        v = armazem.carregar_video("2026-11-16-a")
        self.assertEqual(v.status, Status.APROVADO)
        self.assertEqual(v.retomar_em, t + timedelta(hours=20, minutes=1))
        m.tick(t + timedelta(hours=5))  # ainda cedo
        self.assertEqual(pub.subidos, [])
        m.tick(t + timedelta(hours=21))
        v = armazem.carregar_video("2026-11-16-a")
        self.assertEqual(v.status, Status.AGENDADO_NO_CANAL)
        self.assertEqual(v.id_externo, "yt-ok")
        self.assertIsNone(v.retomar_em)

    def test_erro_repetido_marca_falhou_sem_derrubar_o_tick(self):
        pub = QuebradoNaCota(99, RuntimeError("rede"))
        armazem, m, t = self.montar(pub)
        for i in range(3):
            m.tick(t + timedelta(minutes=10 * (i + 1)))
        v = armazem.carregar_video("2026-11-16-a")
        self.assertEqual(v.status, Status.FALHOU)
        self.assertIn("rede", v.erro)


if __name__ == "__main__":
    unittest.main()
