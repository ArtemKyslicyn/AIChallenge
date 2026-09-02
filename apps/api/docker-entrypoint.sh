#!/bin/sh
set -eu
MEDIA_DIR="${MEDIA_DIR:-/app/data/media}"
mkdir -p "$MEDIA_DIR"
# Named Docker volumes are often root-owned; app runs as uid 10001.
if [ "$(id -u)" = "0" ]; then
  chown -R appuser:appuser "$MEDIA_DIR" || true
  # Drop root with a clean login-like env (HOME must not stay /root —
  # asyncpg probes ~/.postgresql/* and PermissionError kills boot).
  export HOME=/home/appuser
  export USER=appuser
  export LOGNAME=appuser
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid=appuser --regid=appuser --init-groups -- "$@"
  fi
  exec runuser -u appuser -- "$@"
fi
exec "$@"
