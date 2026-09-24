#!/usr/bin/env bash
# Arranca la API (:8787) y la UI (:3000) juntas; Ctrl+C detiene ambas.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "Falta .env (cp .env.example .env y pon HF_API_KEY)"; exit 1; }
[ -f web/.env.local ] || { echo "Falta web/.env.local (uv run hf-studio create-key web-ui y cópiala ahí)"; exit 1; }
[ -d web/node_modules ] || (cd web && pnpm install)

uv run hf-studio check-credentials

trap 'kill 0' EXIT
uv run hf-studio serve --port 8787 &
# Solo en local: la clave de la UI puede ver todo (see-all) y el proxy no autentica al visitante.
(cd web && pnpm dev --port 3000) &  # el script dev ya liga a 127.0.0.1
wait
