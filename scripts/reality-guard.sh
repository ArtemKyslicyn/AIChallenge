#!/usr/bin/env bash
# Watchdog: keep VLESS Reality camouflage healthy.
# If nginx :8443 is up but local Reality fallthrough on :443 fails → restart xray.
# Never touches docker app stacks. Never prints secrets.
set -euo pipefail

HOST="${PUBLIC_HOST:-aichallenge.arcilite.ru}"
STATE_DIR=/var/lib/reality-guard
LOG=/var/log/reality-guard.log
MAX_RESTARTS_PER_HOUR="${MAX_RESTARTS_PER_HOUR:-3}"
mkdir -p "$STATE_DIR"
touch "$LOG"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) $*" | tee -a "$LOG" >/dev/null; }

http_code() {
  local url=$1
  shift
  curl -sS -o /dev/null -w "%{http_code}" --max-time 8 "$@" "$url" || echo "000"
}

# Rate-limit restarts
count_recent_restarts() {
  local cutoff
  cutoff=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)
  if [[ -f "$STATE_DIR/restarts.log" ]]; then
    awk -v c="$cutoff" '$0 >= c {n++} END{print n+0}' "$STATE_DIR/restarts.log"
  else
    echo 0
  fi
}

systemctl is-active --quiet nginx || { log "nginx_down"; exit 0; }
systemctl is-active --quiet xray || { log "xray_down_attempt_start"; systemctl start xray || true; exit 0; }

code8443="$(http_code "https://127.0.0.1:8443/" -k -H "Host: ${HOST}")"
code443="$(http_code "https://${HOST}/" --resolve "${HOST}:443:127.0.0.1")"

if [[ "$code8443" != "200" ]]; then
  log "skip_restart reason=nginx8443_bad code=${code8443}"
  exit 0
fi

if [[ "$code443" == "200" ]]; then
  # Healthy camouflage path
  exit 0
fi

n="$(count_recent_restarts)"
if (( n >= MAX_RESTARTS_PER_HOUR )); then
  log "reality_broken code443=${code443} but restart_budget_exhausted n=${n}"
  exit 1
fi

log "reality_broken code443=${code443} code8443=${code8443} action=restart_xray"
date -u +%Y-%m-%dT%H:%M:%SZ >>"$STATE_DIR/restarts.log"
systemctl restart xray
sleep 2
code_after="$(http_code "https://${HOST}/" --resolve "${HOST}:443:127.0.0.1")"
log "after_restart code443=${code_after}"
[[ "$code_after" == "200" ]]
