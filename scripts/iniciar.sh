#!/usr/bin/env bash
# Roda a fábrica direto no seu computador (Linux/macOS): cria o ambiente, confere tudo e sobe o painel.
#   ./scripts/iniciar.sh            → provedores/publicador conforme o seu .env
#   ./scripts/iniciar.sh --demo     → dia inventado, sem chaves e sem gastos
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet ".[real]"

if [ "${1:-}" = "--demo" ]; then
  export FABRICA_DADOS=dados-demo FABRICA_CANAIS=canais-demo.json FABRICA_SAIDA=saida-demo
  [ -n "${FABRICA_PAINEL_CHAVE:-}" ] || export FABRICA_PAINEL_CHAVE="demo-$(python -c 'import secrets;print(secrets.token_hex(8))')"
  python -m fabrica demo
  echo; echo "Abra: http://127.0.0.1:${PORT:-8080}/?k=${FABRICA_PAINEL_CHAVE}"; echo
  exec python -m fabrica painel
fi

[ -f .env ] || { cp .env.example .env; echo "Criei o .env — preencha as chaves e rode de novo."; exit 1; }
[ -f canais.json ] || { cp canais.example.json canais.json; echo "Criei canais.json de exemplo — edite com os SEUS canais."; }
python -m fabrica doctor || { echo; echo "Resolva os itens ❌ acima e rode de novo."; exit 1; }
exec python -m fabrica painel --com-maestro
