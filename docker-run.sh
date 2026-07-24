#!/usr/bin/env bash
# TeleDecision Orchestrator -- Docker helper script.
#
# Fully zero-touch: builds, starts Postgres, waits for it to be healthy,
# runs `alembic upgrade head`, seeds default roles/permissions/escalation
# policies/base rule pack (all idempotent -- safe to run every time, they
# skip anything already present), then starts the API. You never need to
# run alembic or the seed scripts by hand.
#
# Usage:
#   ./docker-run.sh              build + migrate + seed + start (foreground, logs streaming)
#   ./docker-run.sh --dev        same, but the dev container (hot reload, source bind-mounted)
#   ./docker-run.sh --detach     start in the background instead of streaming logs
#   ./docker-run.sh --logs       tail logs of the already-running compose stack
#   ./docker-run.sh --down       stop and remove the compose stack
#
# Requires Docker Desktop (or Docker Engine) with the Compose v2 plugin.
# Run this from the project root (the folder containing Dockerfile, docker-compose.yml).

set -euo pipefail

MODE="prod"
DETACH=false
ACTION="up"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev) MODE="dev"; shift ;;
    --detach|-d) DETACH=true; shift ;;
    --logs) ACTION="logs"; shift ;;
    --down) ACTION="down"; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Install Docker Desktop (https://www.docker.com/products/docker-desktop/) and try again." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 plugin not found (checked 'docker compose version')." >&2
  echo "Docker Desktop bundles it; if you're on a bare Docker Engine install, see:" >&2
  echo "  https://docs.docker.com/compose/install/" >&2
  exit 1
fi

if [[ ! -f "Dockerfile" || ! -f "docker-compose.yml" ]]; then
  echo "Run this from the project root (the folder with Dockerfile, docker-compose.yml)." >&2
  exit 1
fi

COMPOSE_FILES=(-f docker-compose.yml)
if [[ "$MODE" == "dev" ]]; then
  COMPOSE_FILES=(-f docker-compose.dev.yml)
fi

case "$ACTION" in
  down)
    echo "Stopping and removing the compose stack ..."
    docker compose "${COMPOSE_FILES[@]}" down
    ;;

  logs)
    docker compose "${COMPOSE_FILES[@]}" logs -f
    ;;

  up)
    echo "Building ($MODE mode) ..."
    docker compose "${COMPOSE_FILES[@]}" build

    echo "Starting Postgres and waiting for it to be healthy ..."
    docker compose "${COMPOSE_FILES[@]}" up -d --wait db

    echo "Applying database migrations (alembic upgrade head) ..."
    docker compose "${COMPOSE_FILES[@]}" run --rm --no-deps api alembic upgrade head

    echo "Seeding defaults (idempotent -- skips anything already present) ..."
    docker compose "${COMPOSE_FILES[@]}" run --rm --no-deps api python scripts/seed_default_roles_permissions.py
    docker compose "${COMPOSE_FILES[@]}" run --rm --no-deps api python scripts/seed_escalation_policies.py
    docker compose "${COMPOSE_FILES[@]}" run --rm --no-deps api python scripts/seed_base_rule_pack.py

    echo "Starting the API ..."
    if [[ "$DETACH" == true ]]; then
      docker compose "${COMPOSE_FILES[@]}" up -d api
      echo ""
      echo "Running in the background. API: http://127.0.0.1:${PORT:-8000}"
      echo "  Docs:   http://127.0.0.1:${PORT:-8000}/docs"
      echo "  Health: http://127.0.0.1:${PORT:-8000}/health"
      echo "  Logs:   ./docker-run.sh --logs"
      echo "  Stop:   ./docker-run.sh --down"
    else
      echo "API will be at http://127.0.0.1:${PORT:-8000}. Ctrl+C to stop."
      docker compose "${COMPOSE_FILES[@]}" up api
    fi
    ;;
esac
