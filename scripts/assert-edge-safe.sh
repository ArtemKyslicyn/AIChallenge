#!/usr/bin/env bash
# Fail closed if a deploy would (or already did) break the public edge.
# Safe to run locally against compose files, or on the VPS before rolling up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Repo checkout vs /usr/local/sbin install.
if [[ -f "$SCRIPT_DIR/../docker-compose.prod.yml" ]]; then
  DEFAULT_COMPOSE="$(cd "$SCRIPT_DIR/.." && pwd)/docker-compose.prod.yml"
elif [[ -f /opt/aichallenge/docker-compose.prod.yml ]]; then
  DEFAULT_COMPOSE=/opt/aichallenge/docker-compose.prod.yml
else
  DEFAULT_COMPOSE=""
fi
COMPOSE="${COMPOSE_FILE:-$DEFAULT_COMPOSE}"
STRICT_HOST="${STRICT_HOST:-0}"

die() { echo "EDGE_GUARD_FAIL: $*" >&2; exit 1; }
ok() { echo "EDGE_GUARD_OK: $*"; }

[[ -n "$COMPOSE" && -f "$COMPOSE" ]] || die "compose not found (set COMPOSE_FILE=...)"

# Product containers must never publish the /nginx edge ports.
if grep -E '["'\'']([0-9.:\[\]]*):(443|8443):' "$COMPOSE" >/dev/null 2>&1 \
  || grep -E '-\s+"?443:?|"8443:|"0\.0\.0\.0:443|"\[::\]:443' "$COMPOSE" >/dev/null 2>&1; then
  die "$COMPOSE publishes :443 or :8443 — those belong to /nginx"
fi
ok "compose does not bind :443/:8443"

# Web must stay on loopback in prod compose.
if ! grep -q '127.0.0.1:18080:80' "$COMPOSE"; then
  die "$COMPOSE must publish web as 127.0.0.1:18080:80"
fi
ok "web published on loopback :18080"

if [[ "$STRICT_HOST" != "1" ]]; then
  exit 0
fi

# Host-only checks (VPS).
command -v ss >/dev/null || die "ss missing"
command -v systemctl >/dev/null || die "systemctl missing"

systemctl is-active --quiet nginx || die "nginx is not active"
systemctl is-active --quiet  || die " is not active"
ok "nginx +  active"

ss -lntp | grep -qE ':443\b.*' || die "port :443 is not owned by "
ss -lntp | grep -qE ':8443\b.*nginx' || die "port :8443 is not owned by nginx"
ok "port owners: 443=, 8443=nginx"

#  dest must remain host nginx (), not a random upstream.
python3 - <<'PY' || die " dest/serverNames invalid"
import json, sys
from pathlib import Path
p = Path("/usr/local/etc//config.json")
cfg = json.loads(p.read_text())
for inbound in cfg.get("inbounds") or []:
    if inbound.get("port") != 443:
        continue
    r = (inbound.get("streamSettings") or {}).get("Settings") or {}
    dest = str(r.get("dest") or "")
    names = list(r.get("serverNames") or [])
    if dest not in {"127.0.0.1:8443", "localhost:8443"}:
        print(f"bad dest={dest!r}", file=sys.stderr)
        sys.exit(2)
    required = {"aichallenge.arcilite.ru"}
    missing = sorted(required - set(names))
    if missing:
        print(f"missing serverNames={missing}", file=sys.stderr)
        sys.exit(3)
    print("_ok")
    break
else:
    print("no :443  inbound", file=sys.stderr)
    sys.exit(4)
PY
ok " dest=127.0.0.1:8443 and required serverNames present"

if curl -sf --max-time 5 "http://127.0.0.1:18080/api/v1/health" >/dev/null; then
  ok "loopback :18080 healthy"
elif [[ "${REQUIRE_LOOPBACK_HEALTH:-0}" == "1" ]]; then
  die "loopback web/api health failed on :18080"
else
  echo "EDGE_GUARD_WARN: loopback :18080 unhealthy (allowed before rolling web recreate)"
fi

# Local  fallthrough (hairpin) — the  path.
HOST="${PUBLIC_HOST:-aichallenge.arcilite.ru}"
code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 \
  --resolve "${HOST}:443:127.0.0.1" "https://${HOST}/" || true)"
[[ "$code" == "200" ]] || die "local  fallthrough https://${HOST}/ via 127.0.0.1:443 => HTTP ${code}"
ok "local  fallthrough HTTP 200"

code8443="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 \
  -k "https://127.0.0.1:8443/" -H "Host: ${HOST}" || true)"
[[ "$code8443" == "200" ]] || die "nginx :8443 Host ${HOST} => HTTP ${code8443}"
ok "nginx :8443 HTTP 200"

exit 0
