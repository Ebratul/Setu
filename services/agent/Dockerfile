# syntax=docker/dockerfile:1.7
# Setu agent (FastAPI). Python 3.13 to match pyproject; deps from uv.lock; non-root runtime.
#
# The image mirrors the repo layout (the app resolves REPO_ROOT as two levels above services/agent
# for data/demo and docs/submission), so build with the repo root as a NAMED CONTEXT:
#   docker build --build-context repo=. -t setu-agent \
#     --build-arg GIT_SHA=$(git rev-parse --short=7 HEAD) --build-arg BUILD_TIME=$(date -u +%FT%TZ) \
#     services/agent
# (docker compose does this for you: additional_contexts: repo: .)

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
ENV PATH="/app/services/agent/.venv/bin:$PATH"
WORKDIR /app/services/agent
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Fetch the multilingual embedding model now, so the first request never downloads anything.
ARG KB_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV KB_EMBEDDING_MODEL=${KB_EMBEDDING_MODEL} KB_MODEL_CACHE_DIR=/opt/setu-fastembed
RUN python -c "import os; from fastembed import TextEmbedding; m = TextEmbedding(os.environ['KB_EMBEDDING_MODEL'], cache_dir=os.environ['KB_MODEL_CACHE_DIR']); print(len(list(m.embed(['warm up']))[0]), 'dims')"

FROM python:${PYTHON_VERSION}-slim AS runtime
ARG KB_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ARG GIT_SHA=unknown
ARG BUILD_TIME=
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/services/agent/.venv/bin:$PATH" \
    PORT=8000 UVICORN_WORKERS=2 GRACEFUL_TIMEOUT=20 \
    FORWARDED_ALLOW_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16" \
    KB_EMBEDDING_MODEL=${KB_EMBEDDING_MODEL} KB_MODEL_CACHE_DIR=/opt/setu-fastembed \
    GIT_SHA=${GIT_SHA} BUILD_TIME=${BUILD_TIME}

RUN groupadd --system --gid 10001 setu \
 && useradd --system --uid 10001 --gid setu --home-dir /app --shell /usr/sbin/nologin setu \
 && mkdir -p /app/keys /app/services/agent/storage \
 && chmod 700 /app/keys

WORKDIR /app/services/agent
COPY --from=builder --chown=setu:setu /app/services/agent/.venv ./.venv
COPY --from=builder --chown=setu:setu /opt/setu-fastembed /opt/setu-fastembed
COPY --chown=setu:setu alembic.ini ./
COPY --chown=setu:setu alembic ./alembic
COPY --chown=setu:setu app ./app
COPY --chown=setu:setu seed ./seed
COPY --chown=setu:setu kb ./kb
COPY --chown=setu:setu config ./config
COPY --chown=setu:setu synthetic ./synthetic
# Repo-level files the app reads at runtime (demo script + replay fixtures + sample documents,
# the committed audit public key).
COPY --from=repo --chown=setu:setu data/demo /app/data/demo
COPY --from=repo --chown=setu:setu docs/submission/audit-public-key.pem /app/docs/submission/audit-public-key.pem
RUN chown setu:setu /app /app/keys /app/services/agent/storage /app/services/agent/kb/sources/generated 2>/dev/null || true

USER setu
EXPOSE 8000
VOLUME ["/app/services/agent/storage", "/app/keys"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4).status == 200 else 1)"

# --workers: each worker is a process with its own in-memory rate limits (see app/api/ratelimit.py).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS} --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS}\" --timeout-graceful-shutdown ${GRACEFUL_TIMEOUT} --timeout-keep-alive 5"]
