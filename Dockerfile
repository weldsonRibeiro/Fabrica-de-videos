FROM python:3.12-slim

# ffmpeg monta os vídeos; tzdata dá os fusos horários (a agenda é no horário do dono)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 fabrica \
    && mkdir /data && chown fabrica:fabrica /data

WORKDIR /app
COPY pyproject.toml ./
COPY fabrica ./fabrica
RUN pip install --no-cache-dir ".[real]"
COPY canais.example.json ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FABRICA_HOST=0.0.0.0 \
    FABRICA_DADOS=/data/dados \
    FABRICA_SAIDA=/data/saida \
    FABRICA_CANAIS=/data/canais.json \
    FABRICA_FUSO=America/Sao_Paulo

VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/saude' % os.environ.get('PORT','8080'), timeout=3)"

ENTRYPOINT ["entrypoint.sh"]
CMD []
