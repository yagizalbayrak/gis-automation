FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# vite.config.ts's build.outDir points at ../src/ageo/interface/web/dist,
# i.e. /app/src/ageo/interface/web/dist from this WORKDIR.
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY --from=frontend-builder /app/src/ageo/interface/web/dist ./src/ageo/interface/web/dist
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm

RUN useradd --create-home ageo && \
    mkdir /home/ageo/.ageo && \
    chown ageo:ageo /home/ageo/.ageo

WORKDIR /app
COPY --from=builder --chown=ageo:ageo /app /app

USER ageo

ENV PATH="/app/.venv/bin:$PATH" \
    AGEO_HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

CMD ["python", "-m", "ageo.interface.api.serve"]
