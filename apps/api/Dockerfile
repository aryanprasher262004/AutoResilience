# Engine image for the local stack (compose.yaml). Reproducible: base images pinned by
# digest, Python dependencies installed exactly from uv.lock (--frozen), no dev tools.
# One process: the in-process reconciler assumes a single API worker.
FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && rm /usr/local/bin/uv
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
ENV PATH=/app/.venv/bin:$PATH
# Any non-root uid works (compose.yaml maps the host user so the kubeconfig is readable).
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
