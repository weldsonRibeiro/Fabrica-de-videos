#!/usr/bin/env bash
# Gera vercel/vercel.json apontando para o endereço público da fábrica.
#   ./scripts/vercel-configurar.sh https://minha-fabrica.up.railway.app
set -euo pipefail
cd "$(dirname "$0")/.."

ORIGEM="${1:-}"
if [[ ! "$ORIGEM" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; then
  echo "Uso: $0 https://endereco-da-fabrica   (https, sem barra no final e sem caminho)" >&2
  exit 1
fi
if [[ "$ORIGEM" =~ \.vercel\.app$ ]]; then
  echo "O destino não pode ser a própria Vercel (criaria um laço). Use o endereço do servidor da fábrica." >&2
  exit 1
fi

sed "s#__ORIGEM__#${ORIGEM}#" vercel/vercel.template.json > vercel/vercel.json
python3 -c "import json; json.load(open('vercel/vercel.json'))"
echo "Criado vercel/vercel.json → ${ORIGEM}"
echo
echo "Próximos passos (veja docs/DEPLOY.md, seção D):"
echo "  1) git add vercel/vercel.json && git commit -m 'Painel na Vercel' && git push"
echo "  2) Vercel → Add New Project → este repositório → Root Directory: vercel → Deploy"
echo "  3) Abra https://SEU-PROJETO.vercel.app/?k=SUA_CHAVE"
