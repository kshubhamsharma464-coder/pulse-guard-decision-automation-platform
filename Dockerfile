# TeleDecision Orchestrator -- production image
#
# Multi-stage build: dependencies are compiled/installed in a throwaway
# builder stage, then only the installed packages + application code are
# copied into a slim runtime stage. Keeps the final image small and avoids
# shipping build tooling into production.

# ---- builder ----
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime ----
FROM python:3.11-slim

# Non-root user -- never run the app as root in a container.
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# Installed dependencies from the builder stage.
COPY --from=builder /install /usr/local

# Application code -- no tests/ or docs/ in the runtime image. migrations/,
# alembic.ini, and scripts/ ARE included (unlike before) so that
# `docker compose run --rm api alembic upgrade head` and the seed scripts
# referenced at the bottom of docker-compose.yml actually work against this
# image instead of failing with "alembic.ini not found".
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini .

COPY docker-entrypoint.sh .

RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
