#!/usr/bin/env bash
# Deploy AIChallenge on the VPS. Run from the repo root on the server.
#
# SAFE DEPLOY PROTOCOL (VLESS / Reality):
# - Do NOT stop host nginx, xray, or free :443/:8443.
# - Do NOT run `docker compose down` (drops :18080 → public 502 / Reality fallthrough pain).
# - Only rebuild/recreate app services; xray owns public :443 → 127.0.0.1:8443 → nginx → :18080.
# - Preflight: scripts/assert-edge-safe.sh (compose + optional STRICT_HOST=1).
# - After up: verify Reality fallthrough; if broken while :8443 OK, reality-guard may restart xray.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BRANCH="${DEPLOY_BRANCH:-main}"
HOST="${PUBLIC_HOST:-aichallenge.arcilite.ru}"

echo "==> edge preflight (compose)"
bash "$ROOT/scripts/assert-edge-safe.sh"

echo "==> fetch / reset to origin/${BRANCH}"
git fetch --prune origin
git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"

if [[ ! -f .env ]]; then
  echo "ERROR: ${ROOT}/.env missing. Create it from .env.example on the server (never in git)." >&2
  exit 1
fi

# Re-run after reset in case compose changed on the branch.
bash "$ROOT/scripts/assert-edge-safe.sh"

# Drop macOS AppleDouble / Finder junk that can break Alembic (null bytes in versions/).
echo "==> remove macOS metadata junk if present"
find "$ROOT" \( -name '._*' -o -name '.DS_Store' \) -type f -delete 2>/dev/null || true

if [[ -x /usr/local/sbin/assert-edge-safe.sh ]] || [[ -f "$ROOT/scripts/assert-edge-safe.sh" ]]; then
  echo "==> edge preflight (host STRICT)"
  STRICT_HOST=1 PUBLIC_HOST="$HOST" bash "$ROOT/scripts/assert-edge-safe.sh" || {
    echo "ERROR: host edge guard failed before deploy — refusing to continue" >&2
    exit 3
  }
fi

echo "==> docker compose build + up (prod, rolling — no down)"
docker compose -f docker-compose.prod.yml up --build -d --remove-orphans

echo "==> wait for api health via local web proxy (:18080)"
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:18080/api/v1/health" >/dev/null; then
    echo "local_proxy_healthy"
    docker compose -f docker-compose.prod.yml ps

    echo "==> post-deploy edge guard"
    STRICT_HOST=1 PUBLIC_HOST="$HOST" bash "$ROOT/scripts/assert-edge-safe.sh" || {
      echo "ERROR: edge broken after deploy" >&2
      # If only Reality is wedged, try one guarded restart (same policy as reality-guard).
      code8443="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 -k "https://127.0.0.1:8443/" -H "Host: ${HOST}" || true)"
      code443="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 --resolve "${HOST}:443:127.0.0.1" "https://${HOST}/" || true)"
      if [[ "$code8443" == "200" && "$code443" != "200" ]]; then
        echo "==> Reality fallthrough down; one xray restart via guard"
        if [[ -x /usr/local/sbin/reality-guard.sh ]]; then
          /usr/local/sbin/reality-guard.sh || true
        else
          bash "$ROOT/scripts/reality-guard.sh" || true
        fi
        STRICT_HOST=1 PUBLIC_HOST="$HOST" bash "$ROOT/scripts/assert-edge-safe.sh" || exit 2
      else
        exit 2
      fi
    }

    echo "==> public probe (best-effort; path-dependent)"
    code443="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 "https://${HOST}/" || true)"
    code8443="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "https://${HOST}:8443/" || true)"
    echo "public_443=${code443} public_8443=${code8443}"
    # Local Reality is the source of truth for camouflage; public :8443 may be filtered on some ISPs.
    exit 0
  fi
  sleep 2
done

echo "ERROR: health check failed" >&2
docker compose -f docker-compose.prod.yml logs --tail=80
exit 1
