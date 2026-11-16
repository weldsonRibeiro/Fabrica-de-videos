import base64
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

from fabrica.armazem import Armazem
from fabrica.config import Config, ErroDeConfiguracao
from fabrica.modelos import Etapa, Status, Video
from fabrica.pipeline import Pipeline
from fabrica.provedores.base import LimiteAtingido
from fabrica.provedores.claude import ClienteClaude, ErroDeIA, validar_roteiro
from fabrica.provedores.openai_http import ClienteOpenAI

try:
    import anthropic
    try:
        import httpx2 as httpx
    except ImportError:
        import httpx
except ImportError:  # extra opcional não instalado
    anthropic = None

TEM_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

ROTEIRO = {
    "titulos": ["T1", "T2", "T3"],
    "descricao": "desc",
    "cenas": [{"narracao": f"cena {i}", "prompt_imagem": f"img {i}"} for i in range(3)],
    "thumbnails": ["th1", "th2", "th3"],
    "shorts": [
        {"titulo": "s1", "cena_inicio": 0, "cena_fim": 1},
        {"titulo": "invalido", "cena_inicio": 2, "cena_fim": 9},
    ],
}


def resposta(texto="", stop="end_turn", entrada=1000, saida=2000, buscas=0):
    return NS(
        content=[NS(type="text", text=texto)], stop_reason=stop,
        usage=NS(input_tokens=entrada, output_tokens=saida, server_tool_use=NS(web_search_requests=buscas)),
    )


class ClienteFalso:
    """Imita client.beta.messages.stream(...) do SDK."""

    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **kw):
        self.chamadas.append(kw)
        item = self.respostas.pop(0)

        class Fluxo:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def get_final_message(s):
                if isinstance(item, Exception):
                    raise item
                return item

        return Fluxo()


@unittest.skipIf(anthropic is None, "pip install '.[real]'")
class TestClaude(unittest.TestCase):
    def test_roteiro_usa_esquema_fallback_e_calcula_custo(self):
        c = ClienteFalso(resposta(json.dumps(ROTEIRO)))
        claude = ClienteClaude(Config(), c)
        roteiro, custo = claude.roteirizar("tema", "nicho", "dossiê")
        kw = c.chamadas[0]
        self.assertEqual(kw["model"], "claude-opus-5-5")
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kw["fallbacks"], "default")
        self.assertNotIn("thinking", kw)
        self.assertAlmostEqual(custo, (1000 * 4 + 2000 * 20) / 1e6)
        self.assertEqual(len(roteiro["shorts"]), 1)  # o short com índice fora do intervalo foi descartado

    def test_fallback_pode_ser_desligado(self):
        c = ClienteFalso(resposta(json.dumps(ROTEIRO)))
        ClienteClaude(Config(fallback=False), c).roteirizar("t", "n", "d")
        self.assertNotIn("fallbacks", c.chamadas[0])

    def test_pesquisa_continua_apos_pause_turn_e_soma_buscas(self):
        pausa = resposta("parte 1", stop="pause_turn", buscas=2)
        pausa.content.append(NS(type="web_search_tool_result", content=[NS(url="https://a.com")]))
        c = ClienteFalso(pausa, resposta("parte 2"))
        r = ClienteClaude(Config(), c).pesquisar("tema", "nicho")
        self.assertEqual(r.texto, "parte 1parte 2")
        self.assertEqual(r.fontes, ["https://a.com"])
        self.assertEqual(len(c.chamadas), 2)
        self.assertEqual(c.chamadas[0]["tools"][0]["type"], "web_search_20260209")
        self.assertGreater(r.custo, 0.02)

    def test_rate_limit_vira_limite_atingido_com_retry_after(self):
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        erro = anthropic.RateLimitError("limite", response=httpx.Response(429, headers={"retry-after": "120"}, request=req), body=None)
        with self.assertRaises(LimiteAtingido) as ctx:
            ClienteClaude(Config(), ClienteFalso(erro)).pesquisar("t", "n")
        self.assertEqual(ctx.exception.esperar, timedelta(seconds=120))

    def test_recusa_e_truncamento_viram_erro(self):
        for stop in ("refusal", "max_tokens"):
            with self.assertRaises(ErroDeIA):
                ClienteClaude(Config(), ClienteFalso(resposta("x", stop=stop))).pesquisar("t", "n")

    def test_validar_roteiro_sem_cenas(self):
        with self.assertRaises(ErroDeIA):
            validar_roteiro({"cenas": [], "titulos": ["a"], "thumbnails": ["b"], "shorts": []})


class TestConfig(unittest.TestCase):
    def test_exige_chave_openai(self):
        with self.assertRaises(ErroDeConfiguracao):
            Config.do_ambiente({})
        c = Config.do_ambiente({"OPENAI_API_KEY": "k", "FABRICA_MODELO": "claude-sonnet-5-5", "FABRICA_SEM_FALLBACK": "1"})
        self.assertEqual(c.modelo, "claude-sonnet-5-5")
        self.assertFalse(c.fallback)


@unittest.skipUnless(TEM_FFMPEG and anthropic, "precisa de ffmpeg e do extra 'real'")
class TestProvedorRealPonteAPonte(unittest.TestCase):
    """Fábrica inteira com Claude e OpenAI simulados e ffmpeg de verdade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        sub = lambda *a: subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *a], check=True)  # noqa: E731
        sub("-f", "lavfi", "-i", "testsrc2=s=1536x1024", "-frames:v", "1", str(self.raiz / "img.png"))
        sub("-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(self.raiz / "voz.mp3"))
        self.png_b64 = base64.b64encode((self.raiz / "img.png").read_bytes()).decode()
        self.mp3 = (self.raiz / "voz.mp3").read_bytes()
        self.chamadas = []
        self.falhar_imagem_na = None

    def transporte(self, url, headers, corpo):
        self.chamadas.append(url.rsplit("/", 2)[-2] + "/" + url.rsplit("/", 1)[-1])
        if url.endswith("/audio/speech"):
            return self.mp3
        n_img = sum(1 for c in self.chamadas if c.endswith("generations"))
        if self.falhar_imagem_na == n_img:
            self.falhar_imagem_na = None
            raise LimiteAtingido(timedelta(minutes=30), "limite de imagens")
        return json.dumps({"data": [{"b64_json": self.png_b64}]}).encode()

    def provedor(self):
        from fabrica.provedores.real import ProvedorReal

        cfg = Config(openai_key="k", saida=self.raiz / "saida")
        claude = ClienteClaude(cfg, ClienteFalso(
            resposta("dossiê completo"), resposta(json.dumps(ROTEIRO)),
        ))
        return ProvedorReal(cfg, claude, ClienteOpenAI("k", self.transporte))

    def test_video_completo_e_retomada_sem_repagar_imagens(self):
        armazem = Armazem(self.raiz / "dados")
        pipeline = Pipeline(self.provedor(), armazem)
        video = Video("v1", "c", "tema", datetime(2026, 11, 16, 5, 30), nicho="nicho")

        self.falhar_imagem_na = 3  # a 3ª imagem de cena bate no limite
        pipeline.rodar(video, datetime(2026, 11, 16, 5, 30))
        self.assertEqual(video.status, Status.PAUSADO)
        self.assertEqual(video.retomar_em, datetime(2026, 11, 16, 6, 0))
        self.assertEqual(set(video.artefatos), {"pesquisa", "roteiro", "narracao"})

        pipeline.rodar(video, datetime(2026, 11, 16, 6, 0))
        self.assertEqual(video.status, Status.AGUARDANDO_APROVACAO)
        imagens = sum(1 for c in self.chamadas if c.endswith("generations"))
        # rodada 1: 3 chamadas (a 3ª falhou); rodada 2: só a cena 3 de novo + 3 thumbnails.
        # As cenas 1 e 2 já estavam em disco e não foram geradas (nem pagas) outra vez.
        self.assertEqual(imagens, 3 + 1 + 3)
        p = video.pacote
        self.assertEqual(len(p["thumbnails"]), 3)
        self.assertEqual(len(p["shorts"]), 1)
        self.assertEqual(p["titulos"], ["T1", "T2", "T3"])
        for caminho in [p["video"], *p["shorts"], *p["thumbnails"]]:
            self.assertTrue(Path(caminho).stat().st_size > 0, caminho)
        # custo = 2 chamadas ao Claude + voz + 6 imagens pagas (3 cenas + 3 thumbs), inclusive as 2 de antes do limite
        self.assertAlmostEqual(video.custo, 2 * 0.044 + 6 * 0.05 + 0.0008, delta=0.005)


if __name__ == "__main__":
    unittest.main()
