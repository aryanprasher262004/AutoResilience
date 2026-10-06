#!/usr/bin/env bash
# Local PostgreSQL for the API, matching the default DATABASE_URL
# (postgresql+psycopg://postgres:postgres@localhost:5432/autoresilience), then
# applies migrations. Idempotent; data lives in the Docker volume below.
set -euo pipefail

NAME=autoresilience-postgres
VOLUME=autoresilience-pgdata
IMAGE=postgres:17-alpine
PORT=${AUTORESILIENCE_DB_PORT:-5432}
ROOT=$(cd "$(dirname "$0")/.." && pwd)

if ! docker container inspect "$NAME" >/dev/null 2>&1; then
  echo "Creating $NAME ($IMAGE) on localhost:$PORT"
  docker run -d --name "$NAME" --restart unless-stopped \
    -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=autoresilience \
    -p "127.0.0.1:$PORT:5432" -v "$VOLUME:/var/lib/postgresql/data" "$IMAGE" >/dev/null
elif [ "$(docker container inspect -f '{{.State.Running}}' "$NAME")" != true ]; then
  echo "Starting $NAME"
  docker start "$NAME" >/dev/null
fi

for _ in $(seq 60); do
  docker exec "$NAME" pg_isready -U postgres -d autoresilience -q && break
  sleep 1
done
docker exec "$NAME" pg_isready -U postgres -d autoresilience -q

export DATABASE_URL=${DATABASE_URL:-postgresql+psycopg://postgres:postgres@localhost:$PORT/autoresilience}
(cd "$ROOT/apps/api" && uv run alembic upgrade head)
echo "PostgreSQL ready: localhost:$PORT/autoresilience"
