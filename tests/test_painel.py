import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
from pathlib import Path

from fabrica.armazem import Armazem
from fabrica.maestro import Maestro
from fabrica.modelos import Canal, Status
from fabrica.painel import Painel
from fabrica.pipeline import Pipeline
from fabrica.provedores.falso import ProvedorFalso, PublicadorFalso

CHAVE = "chave-de-teste-bem-longa-123"


class TestPainel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        self.saida = raiz / "saida"
        self.armazem = Armazem(raiz / "dados")
        canais = [Canal("a", "Canal A", "x", "05:30", ["Tema A"])]
        maestro = Maestro(self.armazem, Pipeline(ProvedorFalso(), self.armazem), canais, PublicadorFalso())
        maestro.tick(datetime(2026, 11, 16, 5, 30))
        self.id = "2026-11-16-a"

        # os provedores falsos não criam arquivos: cria os do pacote dentro da pasta de saída
        v = self.armazem.carregar_video(self.id)
        pasta = self.saida / self.id
        pasta.mkdir(parents=True)
        (pasta / "video.mp4").write_bytes(bytes(range(256)) * 4)  # 1024 bytes
        (pasta / "thumb-1.jpg").write_bytes(b"jpg")
        (self.saida.parent / "segredo.txt").write_text("fora da saída")
        v.pacote.update({"video": str(pasta / "video.mp4"), "thumbnails": [str(pasta / "thumb-1.jpg"), str(raiz / "segredo.txt")]})
        self.armazem.salvar_video(v)

        painel = Painel(self.armazem, canais, CHAVE, self.saida)
        self.servidor = painel.servidor("127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)

        jar = CookieJar()
        self.cliente = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def pedir(self, caminho, cliente=None, **kw):
        req = urllib.request.Request(self.base + caminho, **kw)
        try:
            with (cliente or self.cliente).open(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def entrar(self):
        self.assertEqual(self.pedir(f"/?k={CHAVE}")[0], 200)  # segue o 303 → "/" já com o cookie

    def test_sem_chave_nada_abre(self):
        for caminho in ("/", "/api/estado", f"/media/{self.id}/video/0"):
            self.assertEqual(self.pedir(caminho)[0], 401, caminho)
        self.assertEqual(self.pedir("/?k=errada")[0], 401)

    def test_chave_vira_cookie_e_abre_a_pagina(self):
        status, _, corpo = self.pedir(f"/?k={CHAVE}")
        self.assertEqual(status, 200)
        self.assertIn("Fábrica de Vídeos".encode(), corpo)
        self.assertEqual(self.pedir("/api/estado")[0], 200)

    def test_estado_lista_pendente_com_midia_e_saldo(self):
        self.entrar()
        dados = json.loads(self.pedir("/api/estado")[2])
        self.assertEqual(len(dados["pendentes"]), 1)
        p = dados["pendentes"][0]
        self.assertEqual(p["canal"], "Canal A")
        self.assertEqual(len(p["titulos"]), 3)
        self.assertEqual(p["video"], f"/media/{self.id}/video/0")
        self.assertEqual(dados["saldo"], -6.5)
        self.assertNotIn("titulos", dados["videos"][0])

    def test_video_com_range_para_o_celular(self):
        self.entrar()
        status, h, corpo = self.pedir(f"/media/{self.id}/video/0", headers={"Range": "bytes=10-19"})
        self.assertEqual(status, 206)
        self.assertEqual(h["Content-Range"], "bytes 10-19/1024")
        self.assertEqual(corpo, bytes(range(10, 20)))
        status, _, corpo = self.pedir(f"/media/{self.id}/video/0", headers={"Range": "bytes=-4"})
        self.assertEqual((status, corpo), (206, bytes([252, 253, 254, 255])))
        self.assertEqual(self.pedir(f"/media/{self.id}/video/0", headers={"Range": "bytes=5000-"})[0], 416)
        self.assertEqual(len(self.pedir(f"/media/{self.id}/video/0")[2]), 1024)

    def test_nao_serve_arquivo_fora_da_pasta_de_saida(self):
        self.entrar()
        self.assertEqual(self.pedir(f"/media/{self.id}/thumb/0")[0], 200)
        self.assertEqual(self.pedir(f"/media/{self.id}/thumb/1")[0], 404)  # aponta p/ fora da saída
        self.assertEqual(self.pedir(f"/media/..%2F..%2Fetc/video/0")[0], 404)

    def aprovar(self, **extra):
        corpo = {"video": self.id, "titulo": 1, "thumbnail": 0, "publicar_em": "2026-11-17T18:00", **extra}
        return self.pedir("/api/aprovar", method="POST", data=json.dumps(corpo).encode(),
                          headers={"Content-Type": "application/json", "X-Fabrica": "1"})

    def test_aprovar_pelo_painel_e_o_maestro_publica(self):
        self.entrar()
        status, _, corpo = self.aprovar()
        self.assertEqual(status, 200, corpo)
        v = self.armazem.carregar_video(self.id)
        self.assertEqual(v.status, Status.APROVADO)
        self.assertEqual(v.escolha["titulo"], v.pacote["titulos"][1])
        self.assertEqual(json.loads(self.pedir("/api/estado")[2])["pendentes"], [])

    def test_aprovacao_exige_cabecalho_e_dados_validos(self):
        self.entrar()
        sem_cabecalho = self.pedir("/api/aprovar", method="POST", data=b"{}", headers={"Content-Type": "application/json"})
        self.assertEqual(sem_cabecalho[0], 403)
        self.assertEqual(self.aprovar(titulo=9)[0], 400)
        self.assertEqual(self.aprovar(publicar_em="amanhã")[0], 400)
        self.assertEqual(self.aprovar(video="nao-existe")[0], 400)
        self.assertEqual(self.armazem.carregar_video(self.id).status, Status.AGUARDANDO_APROVACAO)

    def test_aprovar_sem_cookie_e_negado(self):
        status, *_ = self.pedir("/api/aprovar", method="POST", data=b"{}", headers={"X-Fabrica": "1"})
        self.assertEqual(status, 401)

    def test_chave_curta_e_recusada(self):
        with self.assertRaises(ValueError):
            Painel(self.armazem, [], "curta", self.saida)


if __name__ == "__main__":
    unittest.main()
