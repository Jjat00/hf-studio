@echo off
rem HF Studio in one command on Windows. Same as ./dev.sh: runs `uv run hf-studio start`.
rem   dev          API on :8787 and web UI on :3000 (Ctrl+C stops both)
rem   dev api      API only, enough for MCP agents (no Node.js needed)
cd /d "%~dp0"
where uv >nul 2>nul || (echo Missing uv: https://docs.astral.sh/uv/getting-started/installation/ & exit /b 1)
if "%~1"=="api" (uv run hf-studio start --api-only) else (uv run hf-studio start)
