#!/usr/bin/env bash
# Deploy AIChallenge on the VPS. Run from the repo root on the server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${DEPLOY_BRANCH:-main}"

echo "==> fetch / reset to origin/${BRANCH}"
git fetch --prune origin
git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"

if [[ ! -f .env ]]; then
  echo "ERROR: ${ROOT}/.env missing. Create it from .env.example on the server (never in git)." >&2
  exit 1
fi

echo "==> docker compose build + up (prod)"
docker compose -f docker-compose.prod.yml down --remove-orphans || true
docker compose -f docker-compose.prod.yml up --build -d --remove-orphans

echo "==> wait for api health via web proxy"
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1/api/v1/health" >/dev/null; then
    echo "healthy"
    docker compose -f docker-compose.prod.yml ps
    exit 0
  fi
  sleep 2
done

echo "ERROR: health check failed" >&2
docker compose -f docker-compose.prod.yml logs --tail=80
exit 1
