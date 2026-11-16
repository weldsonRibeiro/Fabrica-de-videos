#!/bin/sh
# Prepara o volume /data e inicia a fábrica (painel + maestro no mesmo processo).
set -eu

DADOS="${FABRICA_DADOS:-/data/dados}"
SAIDA="${FABRICA_SAIDA:-/data/saida}"
CANAIS="${FABRICA_CANAIS:-/data/canais.json}"
EXEMPLO="${FABRICA_EXEMPLO:-/app/canais.example.json}"

mkdir -p "$DADOS" "$SAIDA" "$(dirname "$CANAIS")"

# Canais: FABRICA_CANAIS_JSON (conteúdo do canais.json numa variável) manda; senão usa o arquivo do volume;
# na primeira vez, semeia com o exemplo — e avisa, porque são canais de mentirinha.
if [ -n "${FABRICA_CANAIS_JSON:-}" ]; then
  printf '%s' "$FABRICA_CANAIS_JSON" > "$CANAIS"
elif [ ! -f "$CANAIS" ]; then
  cp "$EXEMPLO" "$CANAIS"
  echo "[fabrica] AVISO: usando canais de exemplo em $CANAIS. Edite o arquivo ou defina FABRICA_CANAIS_JSON." >&2
fi

if [ "$(id -u)" = "0" ]; then
  # volumes montados chegam como root: entrega ao usuário comum e abre mão de privilégios
  chown -R fabrica:fabrica "$(dirname "$CANAIS")" "$DADOS" "$SAIDA" 2>/dev/null || true
  exec setpriv --reuid=fabrica --regid=fabrica --init-groups "$0" "$@"
fi

if [ "$#" -eq 0 ]; then
  if [ "${FABRICA_MODO:-}" = "mesa" ]; then
    # Mesa de operações (Bitcoin, SIMULAÇÃO): vigia 24 h + página de status. Para voltar à fábrica de vídeos, apague FABRICA_MODO.
    set -- python -m mesa vigiar --servir --fonte "${MESA_FONTE:-coinbase}" --pasta "${MESA_PASTA:-/data/mesa}"
  else
    set -- python -m fabrica painel --com-maestro   # host/porta/provedor vêm das variáveis de ambiente
  fi
fi
exec "$@"
