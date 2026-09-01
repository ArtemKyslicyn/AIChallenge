#!/usr/bin/env bash
# Allow Docker bridge clients to reach sing-box mixed inbound on the host.
# Run on the VPS after deploy (iptables rules are not persistent unless saved).
set -euo pipefail

BRIDGE_SUBNET="${LLM_PROXY_BRIDGE_SUBNET:-172.18.0.0/16}"
BRIDGE_GW="${LLM_PROXY_BRIDGE_GW:-172.18.0.1}"
PORT="${LLM_PROXY_SINGBOX_PORT:-11083}"

for rule in \
  "-p tcp -s ${BRIDGE_SUBNET} -d ${BRIDGE_GW} --dport ${PORT} -j ACCEPT"; do
  if ! iptables -C INPUT ${rule} 2>/dev/null; then
    iptables -I INPUT ${rule}
    echo "added INPUT ${rule}"
  fi
done
