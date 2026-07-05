FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
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
