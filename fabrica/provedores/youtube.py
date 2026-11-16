"""Publicação no YouTube (Data API v3): upload resumível, thumbnail e agendamento (`publishAt`).

Pontos importantes
- Um token de atualização (refresh token) por canal do YouTube: `YOUTUBE_REFRESH_TOKEN_<ID_DO_CANAL>`.
  Gere com `python -m fabrica youtube-autorizar --canal ID`.
- Cota: cada `videos.insert` custa 1.600 unidades e a cota padrão é 10.000/dia (≈ 6 uploads por dia,
  contando os shorts). Ao estourar, o vídeo fica APROVADO e é tentado de novo depois da virada da cota.
- O upload é resumível: se cair no meio, a próxima tentativa continua de onde parou.
- Cada passo concluído (vídeo, thumbnail, cada short) é gravado em `saida/<video>/publicacao.json`,
  então uma nova tentativa nunca sobe o mesmo vídeo duas vezes.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping
from zoneinfo import ZoneInfo

from ..modelos import Perfil, Video
from .base import LimiteAtingido

URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_AUTORIZACAO = "https://accounts.google.com/o/oauth2/v2/auth"
URL_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
URL_THUMB = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={id}"
ESCOPO = "https://www.googleapis.com/auth/youtube.upload"

TAMANHO_PEDACO = 8 * 1024 * 1024  # múltiplo de 256 KiB, como a API exige
ANTECEDENCIA_MINIMA = timedelta(minutes=10)  # publishAt precisa estar no futuro


class ErroYouTube(Exception):
    pass


# transporte(metodo, url, headers, corpo) -> (status, headers_em_minusculas, corpo) ; injetável nos testes
Resposta = tuple[int, dict[str, str], bytes]
Transporte = Callable[[str, str, dict[str, str], "bytes | None"], Resposta]


def transporte_urllib(metodo: str, url: str, headers: dict[str, str], corpo: bytes | None) -> Resposta:
    req = urllib.request.Request(url, data=corpo, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:  # 308 (retomar) e erros chegam como exceção: devolve como resposta
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
    except urllib.error.URLError as e:
        raise ErroYouTube(f"falha de rede: {e.reason}") from e


def segundos_ate_virada_da_cota(agora: datetime | None = None) -> timedelta:
    """A cota diária do YouTube zera à meia-noite do Pacífico."""
    pt = ZoneInfo("America/Los_Angeles")
    agora = (agora or datetime.now(timezone.utc)).astimezone(pt)
    virada = (agora + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return virada - agora


def _sufixo_env(canal_id: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", canal_id.upper())


@dataclass
class ConfigYouTube:
    client_id: str
    client_secret: str
    refresh_tokens: dict[str, str]          # canal_id -> refresh token
    fuso: str = "America/Sao_Paulo"         # fuso dos horários que você aprova
    categoria: str = "22"                   # 22 = Pessoas e blogs; 27 = Educação; 28 = Ciência e tecnologia
    idioma: str = "pt-BR"
    conteudo_sintetico: bool = True         # declara que há mídia gerada por IA (exigência do YouTube)
    intervalo_shorts: timedelta = timedelta(hours=12)

    @classmethod
    def do_ambiente(cls, canais: list[str], env: Mapping[str, str] | None = None) -> "ConfigYouTube":
        env = os.environ if env is None else env
        faltando = [n for n in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET") if not env.get(n)]
        if faltando:
            raise ErroYouTube(f"defina {', '.join(faltando)} (veja .env.example)")
        tokens = {c: env[f"YOUTUBE_REFRESH_TOKEN_{_sufixo_env(c)}"] for c in canais if env.get(f"YOUTUBE_REFRESH_TOKEN_{_sufixo_env(c)}")}
        return cls(
            client_id=env["YOUTUBE_CLIENT_ID"],
            client_secret=env["YOUTUBE_CLIENT_SECRET"],
            refresh_tokens=tokens,
            fuso=env.get("FABRICA_FUSO", cls.fuso),
            categoria=env.get("YOUTUBE_CATEGORIA", cls.categoria),
            conteudo_sintetico=env.get("FABRICA_SEM_SELO_IA", "") == "",
            intervalo_shorts=timedelta(hours=float(env.get("FABRICA_INTERVALO_SHORTS_H", "12"))),
        )


class PublicadorYouTube:
    def __init__(
        self,
        config: ConfigYouTube,
        saida: Path = Path("saida"),
        transporte: Transporte = transporte_urllib,
        agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.cfg, self.saida, self._http, self._agora = config, saida, transporte, agora

    # --- API pública --------------------------------------------------------------------------
    def agendar(self, video: Video) -> str:
        """Sobe vídeo + thumbnail + shorts, tudo agendado. Devolve o id do vídeo principal."""
        token = self._token(video.canal_id)
        progresso = _Progresso(self.saida / video.id / "publicacao.json")
        titulo = video.escolha["titulo"]
        perfil = Perfil.de_dict(video.perfil)
        quando = self._quando(video.escolha["publicar_em"])

        if "video_id" not in progresso.dados:
            progresso.dados["video_id"] = self._subir(
                token, progresso, "video", Path(video.pacote["video"]),
                titulo, video.pacote.get("descricao", ""), quando, perfil,
            )
            progresso.salvar()
        video_id = progresso.dados["video_id"]

        if not progresso.dados.get("thumbnail"):
            self._thumbnail(token, video_id, Path(video.escolha["thumbnail"]))
            progresso.dados["thumbnail"] = True
            progresso.salvar()

        titulos_shorts = [s["titulo"] for s in video.artefatos.get("roteiro", {}).get("shorts", [])]
        feitos = progresso.dados.setdefault("shorts", [])
        for j, caminho in enumerate(video.pacote.get("shorts", [])):
            if j < len(feitos):
                continue
            nome = titulos_shorts[j] if j < len(titulos_shorts) else f"{titulo} (parte {j + 1})"
            feitos.append(self._subir(
                token, progresso, f"short-{j + 1}", Path(caminho),
                f"{nome[:90]} #Shorts", f"{titulo}\nVídeo completo: https://youtu.be/{video_id}",
                quando + self.cfg.intervalo_shorts * (j + 1), perfil,
            ))
            progresso.salvar()
        return video_id

    # --- internos -----------------------------------------------------------------------------
    def _quando(self, publicar_em: str) -> datetime:
        """Horário aprovado (no fuso do dono) → UTC, nunca no passado."""
        local = datetime.fromisoformat(publicar_em)
        if local.tzinfo is None:
            local = local.replace(tzinfo=ZoneInfo(self.cfg.fuso))
        return max(local.astimezone(timezone.utc), self._agora() + ANTECEDENCIA_MINIMA)

    def _token(self, canal_id: str) -> str:
        refresh = self.cfg.refresh_tokens.get(canal_id)
        if not refresh:
            raise ErroYouTube(
                f"sem refresh token para o canal '{canal_id}' "
                f"(YOUTUBE_REFRESH_TOKEN_{_sufixo_env(canal_id)}; gere com `fabrica youtube-autorizar --canal {canal_id}`)"
            )
        corpo = urllib.parse.urlencode({
            "client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret,
            "refresh_token": refresh, "grant_type": "refresh_token",
        }).encode()
        status, _, dados = self._http("POST", URL_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, corpo)
        if status != 200:
            raise ErroYouTube(f"não foi possível renovar o acesso do canal '{canal_id}' ({status}): {dados[:200]!r}")
        return json.loads(dados)["access_token"]

    def _erro(self, status: int, dados: bytes, contexto: str) -> ErroYouTube | LimiteAtingido:
        try:
            motivos = [e.get("reason") for e in json.loads(dados)["error"]["errors"]]
        except (ValueError, KeyError, TypeError):
            motivos = []
        if status == 403 and ("quotaExceeded" in motivos or "dailyLimitExceeded" in motivos):
            return LimiteAtingido(segundos_ate_virada_da_cota(self._agora()), "cota diária da API do YouTube esgotada")
        if status == 403 and "uploadLimitExceeded" in motivos:
            return LimiteAtingido(timedelta(hours=6), "limite de uploads do canal atingido")
        return ErroYouTube(f"{contexto}: HTTP {status} {motivos or dados[:200]!r}")

    def _subir(self, token: str, progresso: "_Progresso", chave: str, arquivo: Path,
               titulo: str, descricao: str, quando: datetime, perfil: Perfil | None = None) -> str:
        perfil = perfil or Perfil()
        tamanho = arquivo.stat().st_size
        auth = {"Authorization": f"Bearer {token}"}
        sessao = progresso.dados.setdefault("sessoes", {}).get(chave)
        offset = 0

        if sessao:  # tentativa anterior caiu no meio: pergunta até onde chegou
            status, h, dados = self._http("PUT", sessao, {**auth, "Content-Length": "0", "Content-Range": f"bytes */{tamanho}"}, b"")
            if status in (200, 201):
                return json.loads(dados)["id"]
            if status == 308:
                offset = int(h["range"].split("-")[1]) + 1 if "range" in h else 0
            else:
                sessao = None  # sessão expirada: começa outra

        if not sessao:
            metadados = {
                "snippet": {"title": titulo[:100], "description": descricao[:5000],
                            "categoryId": perfil.categoria_youtube or self.cfg.categoria,
                            "defaultLanguage": perfil.idioma or self.cfg.idioma,
                            "defaultAudioLanguage": perfil.idioma or self.cfg.idioma},
                "status": {"privacyStatus": "private",  # agendado: fica privado até o publishAt
                           "publishAt": quando.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "selfDeclaredMadeForKids": False,
                           "containsSyntheticMedia": self.cfg.conteudo_sintetico},
            }
            status, h, dados = self._http("POST", URL_UPLOAD, {
                **auth, "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(tamanho), "X-Upload-Content-Type": "video/mp4",
            }, json.dumps(metadados).encode())
            if status != 200 or "location" not in h:
                raise self._erro(status, dados, f"iniciar upload de {arquivo.name}")
            sessao = h["location"]
            progresso.dados["sessoes"][chave] = sessao
            progresso.salvar()  # guarda a sessão antes de enviar: é o que permite retomar

        with arquivo.open("rb") as f:
            while True:
                f.seek(offset)
                pedaco = f.read(TAMANHO_PEDACO)
                fim = offset + len(pedaco) - 1
                status, h, dados = self._http("PUT", sessao, {
                    **auth, "Content-Length": str(len(pedaco)), "Content-Type": "video/mp4",
                    "Content-Range": f"bytes {offset}-{fim}/{tamanho}" if pedaco else f"bytes */{tamanho}",
                }, pedaco)
                if status in (200, 201):
                    return json.loads(dados)["id"]
                if status != 308:
                    raise self._erro(status, dados, f"enviar {arquivo.name}")
                novo = int(h["range"].split("-")[1]) + 1 if "range" in h else 0
                if novo <= offset and pedaco:
                    raise ErroYouTube(f"upload de {arquivo.name} não avançou (offset {offset})")
                offset = novo

    def _thumbnail(self, token: str, video_id: str, arquivo: Path) -> None:
        status, _, dados = self._http("POST", URL_THUMB.format(id=video_id), {
            "Authorization": f"Bearer {token}", "Content-Type": "image/jpeg",
        }, arquivo.read_bytes())
        if status != 200:
            raise self._erro(status, dados, "enviar thumbnail (o canal precisa estar verificado)")


class _Progresso:
    def __init__(self, caminho: Path):
        self.caminho = caminho
        self.dados: dict = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.caminho)


# --- autorização (uma vez por canal) --------------------------------------------------------------
def autorizar(client_id: str, client_secret: str, porta: int = 8765,
              mostrar: Callable[[str], None] = print, transporte: Transporte = transporte_urllib) -> str:
    """Fluxo OAuth de app instalado: abre o navegador, recebe o código local e devolve o refresh token."""
    import http.server
    import secrets

    estado = secrets.token_urlsafe(16)
    redirect = f"http://127.0.0.1:{porta}"
    url = URL_AUTORIZACAO + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": ESCOPO,
        "access_type": "offline", "prompt": "consent", "state": estado,
    })
    recebido: dict[str, str] = {}

    class Receptor(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            recebido.update({k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Autorizado. Pode fechar esta aba e voltar ao terminal.".encode())

        def log_message(self, *a):
            pass

    mostrar(f"Abra no navegador (entre com a conta DONA DO CANAL) e autorize:\n\n{url}\n")
    with http.server.HTTPServer(("127.0.0.1", porta), Receptor) as servidor:
        servidor.handle_request()
    if recebido.get("state") != estado or "code" not in recebido:
        raise ErroYouTube(f"autorização não concluída: {recebido.get('error', 'resposta inesperada')}")
    corpo = urllib.parse.urlencode({
        "code": recebido["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()
    status, _, dados = transporte("POST", URL_TOKEN, {"Content-Type": "application/x-www-form-urlencoded"}, corpo)
    if status != 200 or "refresh_token" not in json.loads(dados):
        raise ErroYouTube(f"troca do código falhou ({status}): {dados[:200]!r}")
    return json.loads(dados)["refresh_token"]
