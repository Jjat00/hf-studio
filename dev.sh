#!/usr/bin/env bash
# HF Studio in one command (macOS, Linux, WSL). On Windows use dev.cmd. Both run `uv run hf-studio start`.
#   ./dev.sh        API on :8787 and web UI on :3000 (Ctrl+C stops both)
#   ./dev.sh api    API only, enough for MCP agents (no Node.js needed)
# The first run asks for your Higgsfield key (and optionally ElevenLabs) and sets everything up.
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null || { echo "Missing uv: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
case "${1:-}" in
  "") exec uv run hf-studio start ;;
  api) exec uv run hf-studio start --api-only ;;
  *) echo "Usage: ./dev.sh [api]"; exit 2 ;;
esac
