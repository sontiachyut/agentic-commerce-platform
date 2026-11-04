FROM node:22-bookworm-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da AS frontend
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/index.html web/tsconfig*.json web/vite.config.* ./
COPY web/src ./src
RUN npm run build

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS builder
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.5.24
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
RUN groupadd -g 10001 commerce && useradd -u 10001 -g commerce -M commerce
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY src ./src
COPY --from=frontend /web/dist ./web/dist
COPY migrations ./migrations
COPY alembic.ini ./
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8510/health/ready',timeout=2)"
CMD ["python", "-m", "uvicorn", "commerce.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8510", "--no-access-log"]
