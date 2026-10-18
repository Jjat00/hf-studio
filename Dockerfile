# HF Studio en un solo contenedor (Railway, Render, Fly, un VPS…): la API y la UI ya compilada.
# Arranca con `hf-studio cloud`, que exige STUDIO_PASSWORD. Datos (SQLite y archivos) en el volumen /data.

FROM node:22-bookworm-slim AS web
WORKDIR /web
RUN corepack enable && corepack prepare pnpm@10.28.2 --activate
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
ENV HF_STUDIO_STANDALONE=1 NEXT_TELEMETRY_DISABLED=1
RUN pnpm build \
    && cp -r .next/static .next/standalone/.next/static \
    && cp -r public .next/standalone/public

FROM python:3.12-slim-bookworm
# El ffmpeg de Debian trae el filtro rubberband (efectos de voz deep, monster y ghost).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev
COPY --from=web /web/.next/standalone ./web/.next/standalone

RUN useradd --create-home --uid 1000 studio && mkdir -p /data && chown studio /data
USER studio
ENV PATH="/app/.venv/bin:$PATH" \
    DATABASE_URL="sqlite+aiosqlite:////data/hf_studio.db" \
    STORAGE_DIR="/data/files" \
    PORT=3000
VOLUME /data
EXPOSE 3000
CMD ["hf-studio", "cloud"]
