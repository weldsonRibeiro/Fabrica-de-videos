"""Painel de aprovação (mobile-first): vê o vídeo pronto, escolhe título/thumbnail/horário e aprova.

Só biblioteca padrão. Protegido por uma chave (`FABRICA_PAINEL_CHAVE`) que vira cookie na primeira
visita (`/?k=CHAVE`). Sirva atrás de HTTPS (túnel/reverse proxy) se for abrir para a internet.
"""
from __future__ import annotations

import hmac
import json
import mimetypes
import re
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .armazem import Armazem
from .fuso import agora_local
from .jogo import Carteira
from .maestro import aprovar
from .modelos import ETAPAS, Canal, Status, Video

PAGINA = Path(__file__).parent / "web" / "index.html"
COOKIE = "fabrica_chave"
TAMANHO_BLOCO = 1024 * 1024


def _etapa_atual(video: Video) -> str | None:
    """A etapa em andamento (ou onde parou, se pausado): a primeira sem artefato salvo."""
    if video.status not in (Status.EM_PRODUCAO, Status.PAUSADO):
        return None
    return next((e.value for e in ETAPAS if e.value not in video.artefatos), None)


def _json(video: Video, canais: dict[str, Canal], saida: Path) -> dict:
    nome = canais[video.canal_id].nome if video.canal_id in canais else video.canal_id
    base = {
        "id": video.id, "tema": video.tema, "canal": nome, "status": video.status.value,
        "custo": video.custo, "producao_em": video.producao_em.isoformat(),
        "retomar_em": video.retomar_em.isoformat() if video.retomar_em else None, "erro": video.erro,
        "etapa": _etapa_atual(video), "etapas_feitas": len(video.artefatos), "etapas_total": len(ETAPAS),
    }
    if video.status is Status.AGUARDANDO_APROVACAO:
        p = video.pacote
        titulos_shorts = [s["titulo"] for s in video.artefatos.get("roteiro", {}).get("shorts", [])]
        base.update({
            "titulos": p["titulos"], "descricao": p.get("descricao", ""),
            "video": f"/media/{video.id}/video/0",
            "thumbnails": [f"/media/{video.id}/thumb/{i}" for i in range(len(p["thumbnails"]))],
            "shorts": [
                {"url": f"/media/{video.id}/short/{i}",
                 "titulo": titulos_shorts[i] if i < len(titulos_shorts) else f"Short {i + 1}"}
                for i in range(len(p["shorts"]))
            ],
        })
    return base


class Painel:
    def __init__(self, armazem: Armazem, canais: list[Canal], chave: str, saida: Path, fuso: str = "America/Sao_Paulo"):
        if len(chave) < 16:
            raise ValueError("a chave do painel precisa ter pelo menos 16 caracteres")
        self.armazem, self.chave, self.saida, self.fuso = armazem, chave, saida.resolve(), fuso
        self.canais = {c.id: c for c in canais}
        self.trava = threading.Lock()  # dois toques seguidos em "Aprovar" não se atropelam
        # O tick em segundo plano não precisa dessa trava: ele nunca mexe em vídeos AGUARDANDO_APROVACAO.

    # --- regras (testáveis sem HTTP) ----------------------------------------------------------
    def estado(self) -> dict:
        videos = self.armazem.listar_videos()  # leitura segura: os arquivos são trocados de forma atômica
        carteira = Carteira.carregar(self.armazem)
        saldo = carteira.saldo
        pendentes = [_json(v, self.canais, self.saida) for v in videos if v.status is Status.AGUARDANDO_APROVACAO]
        outros = [_json(v, self.canais, self.saida) for v in reversed(videos)]
        for o in outros:  # a lista "na fábrica" não precisa carregar as mídias
            for k in ("titulos", "descricao", "video", "thumbnails", "shorts"):
                o.pop(k, None)
        return {"saldo": saldo, "fuso": self.fuso, "agora": agora_local().isoformat(timespec="seconds"), "pendentes": pendentes, "videos": outros,
                "historico": list(reversed(carteira.historico[-8:]))}

    def aprovar(self, dados: dict) -> None:
        try:
            quando = datetime.fromisoformat(str(dados["publicar_em"]))
            with self.trava:
                aprovar(self.armazem, str(dados["video"]), int(dados["titulo"]), int(dados["thumbnail"]), quando)
        except (KeyError, TypeError) as e:
            raise ValueError(f"campo ausente ou inválido: {e}") from e

    def arquivo_de_midia(self, video_id: str, tipo: str, indice: int) -> Path | None:
        video = self.armazem.carregar_video(video_id)
        if video is None or not video.pacote:
            return None
        lista = {"video": [video.pacote.get("video")], "short": video.pacote.get("shorts", []),
                 "thumb": video.pacote.get("thumbnails", [])}.get(tipo)
        if lista is None or not 0 <= indice < len(lista) or not lista[indice]:
            return None
        caminho = Path(lista[indice]).resolve()
        # só serve o que está dentro da pasta de saída — nada de ../ nem caminho absoluto fora dela
        if not caminho.is_relative_to(self.saida) or not caminho.is_file():
            return None
        return caminho

    # --- HTTP ---------------------------------------------------------------------------------
    def servidor(self, host: str = "127.0.0.1", porta: int = 8080) -> ThreadingHTTPServer:
        return ThreadingHTTPServer((host, porta), _fazer_handler(self))


def _fazer_handler(painel: Painel) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Fabrica"

        def log_message(self, *a):  # silencia o log padrão (não vaza a chave na URL)
            pass

        # -- utilidades
        def _autorizado(self) -> bool:
            for parte in self.headers.get("Cookie", "").split(";"):
                nome, _, valor = parte.strip().partition("=")
                if nome == COOKIE and hmac.compare_digest(valor, painel.chave):
                    return True
            return False

        def _responder(self, status: int, corpo: bytes, tipo: str, extra: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, status: int, dados: dict) -> None:
            self._responder(status, json.dumps(dados, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        # -- rotas
        def do_GET(self):  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/saude":  # para o healthcheck da plataforma; não revela nada
                return self._json(200, {"ok": True})
            chave = parse_qs(url.query).get("k", [""])[0]
            if url.path == "/" and chave:  # primeira visita: troca a chave da URL por um cookie e limpa a URL
                if not hmac.compare_digest(chave, painel.chave):
                    return self._json(401, {"erro": "chave inválida"})
                seguro = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                cookie = f"{COOKIE}={painel.chave}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000{seguro}"
                return self._responder(303, b"", "text/plain", {"Location": "/", "Set-Cookie": cookie})
            if not self._autorizado():
                return self._json(401, {"erro": "não autorizado — abra o link com ?k=SUA_CHAVE"})

            if url.path == "/":
                return self._responder(200, PAGINA.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/estado":
                return self._json(200, painel.estado())
            m = re.fullmatch(r"/media/([\w.-]+)/(video|short|thumb)/(\d+)", url.path)
            if m:
                caminho = painel.arquivo_de_midia(m[1], m[2], int(m[3]))
                if caminho is None:
                    return self._json(404, {"erro": "mídia não encontrada"})
                return self._enviar_arquivo(caminho)
            self._json(404, {"erro": "não encontrado"})

        def do_POST(self):  # noqa: N802
            if not self._autorizado():
                return self._json(401, {"erro": "não autorizado"})
            # cabeçalho customizado + SameSite=Strict: um site de terceiros não consegue forjar a aprovação
            if self.headers.get("X-Fabrica") != "1" or self.path != "/api/aprovar":
                return self._json(403 if self.path == "/api/aprovar" else 404, {"erro": "requisição inválida"})
            try:
                tamanho = int(self.headers.get("Content-Length", "0"))
                if not 0 < tamanho <= 10_000:
                    raise ValueError("corpo inválido")
                painel.aprovar(json.loads(self.rfile.read(tamanho)))
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"erro": str(e)})
            self._json(200, {"ok": True})

        def _enviar_arquivo(self, caminho: Path) -> None:
            tamanho = caminho.stat().st_size
            inicio, fim, status = 0, tamanho - 1, 200
            faixa = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if faixa and (faixa[1] or faixa[2]):  # o Safari/iOS só toca vídeo se houver suporte a Range
                if faixa[1]:
                    inicio = int(faixa[1])
                    fim = min(int(faixa[2]), tamanho - 1) if faixa[2] else tamanho - 1
                else:
                    inicio = max(tamanho - int(faixa[2]), 0)
                if inicio >= tamanho or inicio > fim:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{tamanho}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", mimetypes.guess_type(caminho.name)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fim - inicio + 1))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "private, max-age=3600")
            if status == 206:
                self.send_header("Content-Range", f"bytes {inicio}-{fim}/{tamanho}")
            self.end_headers()
            try:
                with caminho.open("rb") as f:
                    f.seek(inicio)
                    restante = fim - inicio + 1
                    while restante > 0:
                        bloco = f.read(min(TAMANHO_BLOCO, restante))
                        if not bloco:
                            break
                        self.wfile.write(bloco)
                        restante -= len(bloco)
            except (BrokenPipeError, ConnectionResetError):
                pass  # o navegador cancelou (normal ao arrastar a barra do vídeo)

    return Handler


def servir(painel: Painel, host: str, porta: int, tick: Callable[[], None] | None = None, intervalo: float = 60.0) -> None:
    """Sobe o painel; com `tick`, roda também o maestro em segundo plano (um processo só)."""
    servidor = painel.servidor(host, porta)
    parar = threading.Event()
    if tick:
        def laco():
            while not parar.is_set():
                try:
                    tick()
                except Exception as erro:  # noqa: BLE001 — um erro de tick não pode derrubar o painel
                    print(f"[maestro] erro no tick: {erro}", flush=True)
                parar.wait(intervalo)

        threading.Thread(target=laco, daemon=True).start()
    print(f"Painel em http://{host}:{porta}/?k=<sua chave>")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        servidor.server_close()
