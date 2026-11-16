"""Montagem com ffmpeg: cenas (imagem + narração) → vídeo, shorts verticais e thumbnails."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FPS = 30


class ErroFFmpeg(Exception):
    pass


def _rodar(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroFFmpeg(f"{cmd[0]} falhou: {r.stderr.strip()[-600:]}")
    return r.stdout


def exigir_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        raise ErroFFmpeg("ffmpeg/ffprobe não encontrados no PATH")


def duracao(arquivo: Path) -> float:
    saida = _rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arquivo)])
    return float(saida.strip())


def clipe_cena(imagem: Path, audio: Path, saida: Path) -> None:
    """Uma cena: a imagem com zoom lento durante toda a narração (1920x1080)."""
    dur = duracao(audio)
    zoom = (
        "scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,"
        f"zoompan=z='min(zoom+0.0005,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps={FPS},"
        "format=yuv420p"
    )
    _rodar([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(imagem),
        "-i", str(audio),
        "-vf", zoom, "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", f"{dur:.3f}", "-movflags", "+faststart", str(saida),
    ])


def juntar(clipes: list[Path], saida: Path) -> None:
    lista = saida.with_suffix(".txt")
    lista.write_text("".join(f"file '{c.resolve()}'\n" for c in clipes), encoding="utf-8")
    try:
        _rodar(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                "-c", "copy", "-movflags", "+faststart", str(saida)])
    finally:
        lista.unlink(missing_ok=True)


def para_vertical(entrada: Path, saida: Path, max_segundos: int = 59) -> None:
    """9:16 com a cena inteira no centro e o fundo desfocado (não corta o que importa)."""
    filtro = (
        "[0:v]split[a][b];"
        "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
        "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    )
    _rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada), "-t", str(max_segundos),
            "-filter_complex", filtro, "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", str(saida)])


def juntar_audios(audios: list[Path], saida: Path) -> None:
    lista = saida.with_suffix(".txt")
    lista.write_text("".join(f"file '{a.resolve()}'\n" for a in audios), encoding="utf-8")
    try:
        _rodar(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                "-c:a", "libmp3lame", "-b:a", "128k", str(saida)])
    finally:
        lista.unlink(missing_ok=True)


def thumbnail_16x9(entrada: Path, saida: Path) -> None:
    """Padroniza para 1280x720 JPG (formato aceito pelo YouTube, < 2 MB)."""
    _rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada),
            "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720",
            "-q:v", "3", "-frames:v", "1", str(saida)])
